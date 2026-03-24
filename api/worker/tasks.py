import os
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from api.core.celery_app import celery
from api.core.database import SessionLocal
from api.models.file_record import FileRecord
from api.models.folder import Folder
from api.models.outlook_mailbox import OutlookMailbox
from api.models.outlook_message import OutlookMessage
from api.models.outlook_sync_rule import OutlookSyncRule
from api.services.ai import transcribe_audio
from api.services.ingest import extract_text_for_record, replace_knowledge_chunks
from api.services.outlook import (
    attachment_extension,
    attachment_is_supported,
    build_email_document,
    email_record_filename,
    decode_attachment_bytes,
    ensure_valid_access_token,
    fetch_mailbox_messages,
    fetch_message_attachments,
    graph_recipient_addresses,
    graph_sender_address,
    is_removed_message,
    message_external_attachment_id,
    parse_graph_datetime,
    pick_target_project_id,
    safe_filename,
)
from api.services.pst_import import (
    build_email_document as build_pst_email_document,
    cleanup_extracted_tree,
    extract_pst_to_mbox_tree,
    iter_mbox_messages,
    parse_mbox_message,
    safe_attachment_filename,
)
from api.services.csv_import import iter_csv_emails


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
CANCELLED_IMPORT_MESSAGE = "Import cancelled by user."


def _delete_file_if_exists(file_path: Optional[str]):
    if file_path and os.path.exists(file_path):
        os.remove(file_path)


def _delete_file_record(db, record: Optional[FileRecord]):
    if not record:
        return
    for child in list(record.child_files or []):
        _delete_file_record(db, child)
    
    if record.file_path and os.path.exists(record.file_path):
        if record.source_type != "nextcloud":
            # 檢查是否還有其他 FileRecord 正在使用此實體路徑
            other_usage = db.execute(
                select(FileRecord).where(
                    FileRecord.file_path == record.file_path,
                    FileRecord.id != record.id
                )
            ).first()
            if not other_usage:
                os.remove(record.file_path)
    
    db.delete(record)


def _ensure_project(db, name: str):
    from api.models.project import Project

    project = db.execute(select(Project).where(Project.name == name)).scalar_one_or_none()
    if project:
        return project
    project = Project(
        name=name,
        description="Fallback project for Outlook emails that do not match any archive rule.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _ensure_mail_folder(db, project_id: int):
    folder = db.execute(
        select(Folder).where(
            Folder.project_id == project_id,
            Folder.parent_id.is_(None),
            Folder.name == "mail",
        )
    ).scalar_one_or_none()
    if folder:
        return folder

    folder = Folder(name="mail", project_id=project_id, parent_id=None)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def _get_file_record(db, file_record_id: int) -> Optional[FileRecord]:
    return db.execute(select(FileRecord).where(FileRecord.id == file_record_id)).scalar_one_or_none()


def _cancel_requested(db, root_file_id: int) -> bool:
    root_file = _get_file_record(db, root_file_id)
    return bool(root_file and root_file.cancel_requested)


def _mark_import_cancelled(db, root_file_id: int) -> Optional[FileRecord]:
    root_file = _get_file_record(db, root_file_id)
    if not root_file:
        return None
    root_file.status = "cancelled"
    root_file.error_msg = CANCELLED_IMPORT_MESSAGE
    db.commit()
    db.refresh(root_file)
    return root_file


def _upsert_email_file(db, stored_message: OutlookMessage, message: dict, target_project_id: int) -> FileRecord:
    email_file = stored_message.email_file
    if not email_file:
        email_file = db.execute(
            select(FileRecord).where(
                FileRecord.source_type == "outlook_email",
                FileRecord.external_id == message.get("id"),
            )
        ).scalar_one_or_none()

    sent_at = parse_graph_datetime(message.get("sentDateTime"))
    filename = email_record_filename(message.get("subject"), sent_at, fallback_ext=".txt")
    if email_file and email_file.file_path:
        file_path = email_file.file_path
    else:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")

    with open(file_path, "w", encoding="utf-8") as fp:
        fp.write(build_email_document(message))

    file_type = "txt"
    mail_folder = _ensure_mail_folder(db, target_project_id)
    if not email_file:
        email_file = FileRecord(
            filename=filename,
            file_type=file_type,
            file_path=file_path,
            mime_type="text/plain",
            source_type="outlook_email",
            external_id=message.get("id"),
            project_id=target_project_id,
            folder_id=mail_folder.id,
            sender=graph_sender_address(message),
            sent_at=sent_at,
            conversation_id=message.get("conversationId"),
            status="processing",
        )
        db.add(email_file)
        db.flush()
    else:
        email_file.filename = filename
        email_file.file_path = file_path
        email_file.file_type = file_type
        email_file.mime_type = "text/plain"
        email_file.source_type = "outlook_email"
        email_file.external_id = message.get("id")
        email_file.project_id = target_project_id
        email_file.folder_id = mail_folder.id
        email_file.sender = graph_sender_address(message)
        email_file.sent_at = sent_at
        email_file.conversation_id = message.get("conversationId")
        email_file.status = "processing"
        email_file.error_msg = None

    stored_message.email_file = email_file
    return email_file


def _upsert_attachment_file(
    db,
    message: dict,
    attachment: dict,
    target_project_id: int,
    parent_file_id: Optional[int] = None,
) -> Optional[FileRecord]:
    attachment_name = (attachment.get("name") or "").strip()
    content_type = attachment.get("contentType")
    if not attachment_name or not attachment_is_supported(attachment_name, content_type):
        return None

    external_id = message_external_attachment_id(message.get("id"), attachment.get("id"))
    file_record = db.execute(
        select(FileRecord).where(
            FileRecord.source_type == "outlook_attachment",
            FileRecord.external_id == external_id,
        )
    ).scalar_one_or_none()

    file_bytes = decode_attachment_bytes(attachment)
    if not file_bytes:
        return None

    filename = safe_filename(attachment_name, f".{attachment_extension(attachment_name, content_type) or 'bin'}")
    if file_record and file_record.file_path:
        file_path = file_record.file_path
    else:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")

    with open(file_path, "wb") as fp:
        fp.write(file_bytes)

    file_type = attachment_extension(attachment_name, content_type)
    mail_folder = _ensure_mail_folder(db, target_project_id)
    if not file_record:
        file_record = FileRecord(
            filename=filename,
            file_type=file_type,
            file_path=file_path,
            mime_type=content_type,
            source_type="outlook_attachment",
            external_id=external_id,
            project_id=target_project_id,
            folder_id=mail_folder.id,
            parent_file_id=parent_file_id,
            sender=graph_sender_address(message),
            sent_at=parse_graph_datetime(message.get("sentDateTime")),
            conversation_id=message.get("conversationId"),
            status="pending",
        )
        db.add(file_record)
        db.flush()
    else:
        file_record.filename = filename
        file_record.file_type = file_type
        file_record.file_path = file_path
        file_record.mime_type = content_type
        file_record.project_id = target_project_id
        file_record.folder_id = mail_folder.id
        file_record.parent_file_id = parent_file_id
        file_record.sender = graph_sender_address(message)
        file_record.sent_at = parse_graph_datetime(message.get("sentDateTime"))
        file_record.conversation_id = message.get("conversationId")
        file_record.status = "pending"
        file_record.error_msg = None

    return file_record


def _remove_message_artifacts(db, stored_message: OutlookMessage):
    attachment_records = db.execute(
        select(FileRecord).where(
            FileRecord.source_type == "outlook_attachment",
            FileRecord.external_id.like(f"{stored_message.external_message_id}:%"),
        )
    ).scalars().all()
    for record in attachment_records:
        _delete_file_record(db, record)

    if stored_message.email_file:
        email_file = stored_message.email_file
        stored_message.email_file = None
        db.flush()
        _delete_file_record(db, email_file)


def _create_pst_email_file(db, root_file: FileRecord, target_project_id: int, email_item) -> FileRecord:
    mail_folder = _ensure_mail_folder(db, target_project_id)
    filename = email_record_filename(email_item.subject, email_item.sent_at, fallback_ext=".txt")
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")
    with open(file_path, "w", encoding="utf-8") as fp:
        fp.write(build_pst_email_document(email_item))

    file_record = FileRecord(
        filename=filename,
        file_type="txt",
        file_path=file_path,
        mime_type="text/plain",
        source_type="outlook_email",
        external_id=f"pst:{root_file.id}:{email_item.external_id}",
        parent_file_id=root_file.id,
        project_id=target_project_id,
        folder_id=mail_folder.id,
        sender=email_item.sender,
        sent_at=email_item.sent_at,
        conversation_id=email_item.conversation_id,
        status="completed",
    )
    db.add(file_record)
    db.flush()
    return file_record


def _create_pst_attachment_file(db, email_file: FileRecord, target_project_id: int, email_item, attachment) -> FileRecord:
    mail_folder = _ensure_mail_folder(db, target_project_id)
    filename = safe_attachment_filename(attachment.filename)
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")
    with open(file_path, "wb") as fp:
        fp.write(attachment.payload)

    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    is_supported = attachment_is_supported(filename, attachment.content_type) and bool(ext)
    file_record = FileRecord(
        filename=filename,
        file_type=ext or "bin",
        file_path=file_path,
        mime_type=attachment.content_type,
        source_type="outlook_attachment",
        external_id=f"{email_file.external_id}:{filename}",
        parent_file_id=email_file.id,
        project_id=target_project_id,
        folder_id=mail_folder.id,
        sender=email_item.sender,
        sent_at=email_item.sent_at,
        conversation_id=email_item.conversation_id,
        status="pending" if is_supported else "completed",
        error_msg=None if is_supported else "Skipped text extraction for unsupported attachment type.",
    )
    db.add(file_record)
    db.flush()
    return file_record


@celery.task(name="process_document_task", bind=True, max_retries=3)
def process_document_task(self, file_record_id: int, file_path: str, metadata: dict | None = None):
  db = SessionLocal()
  try:
    file_record = db.query(FileRecord).filter(FileRecord.id == file_record_id).first()
    if not file_record:
      print(f"FileRecord {file_record_id} not found.")
      return

    file_record.status = "processing"
    db.commit()

    # --- 1. MD5 背景計算與查重 ---
    from api.services.utils import calculate_md5_from_path
    md5_hash = calculate_md5_from_path(file_path)
    file_record.md5_hash = md5_hash

    # 檢查同專案中是否已有相同內容且已完成處理的檔案
    stmt_existing = select(FileRecord).where(
      FileRecord.md5_hash == md5_hash,
      FileRecord.project_id == file_record.project_id,
      FileRecord.status == "completed",
      FileRecord.id != file_record.id
    ).limit(1)
    existing_record = db.execute(stmt_existing).scalar_one_or_none()

    if existing_record:
      print(f"Duplicate content found for file {file_record_id} (MD5: {md5_hash}). Reusing existing fragments.")
      
      # 判斷是否在同一個資料夾
      if existing_record.folder_id == file_record.folder_id:
        print(f"Same folder duplicate detected. Removing record {file_record_id} to keep folder clean.")
        db.delete(file_record)
        db.commit()
        if os.path.exists(file_path) and file_record.source_type != "nextcloud":
          os.remove(file_path)
        return {"status": "removed_as_duplicate", "orig_id": existing_record.id}

      # 不同資料夾但同專案：保留紀錄，但將路徑重定向到現有檔案，並標記完成
      file_record.status = "completed"
      file_record.file_path = existing_record.file_path # 指向現有的實體檔路徑 (修復 404)
      file_record.error_msg = f"Duplicate content (same MD5 as file {existing_record.id}). Knowledge chunks reused."
      
      # 刪除新產生的冗餘實體檔案以節省空間
      if os.path.exists(file_path) and file_record.source_type != "nextcloud":
        os.remove(file_path)
      
      db.commit()
      return {"status": "duplicate_redirected", "reused_from": existing_record.id}

    # --- 2. 正常處理流程 ---
    db.commit()
    file_type = file_record.file_type.lower()
    print(f"Start processing document: ID={file_record_id}, Type={file_type}, Path={file_path}")

    if file_type == "zip":
      print(f"ZIP file detected. Processing contents for ID={file_record_id}")
      _process_zip_contents(db, file_record, file_path)
      # 依據使用者要求：處理完畢後刪除原本的 .zip 檔與紀錄
      if os.path.exists(file_path) and file_record.source_type != "nextcloud":
        os.remove(file_path)
      db.delete(file_record)
      db.commit()
      return {"status": "zip_processed_and_deleted"}

    elif file_type == "rar":
      print(f"RAR file detected. Processing contents for ID={file_record_id}")
      _process_rar_contents(db, file_record, file_path)
      # 處理完畢後刪除原本的 .rar 檔與紀錄
      if os.path.exists(file_path) and file_record.source_type != "nextcloud":
        os.remove(file_path)
      db.delete(file_record)
      db.commit()
      return {"status": "rar_processed_and_deleted"}

    extracted_text = ""
    audio_extensions = ["mp3", "m4a", "wav", "webm", "mp4"]
    document_extensions = ["pdf", "docx", "doc", "txt", "csv", "xlsx", "xls", "odt"]

    if file_type in audio_extensions:
      extracted_text = transcribe_audio(file_path)
    elif file_type in document_extensions:
      extracted_text = extract_text_for_record(file_record)
    else:
      raise ValueError(f"Unsupported file type: {file_type}")

    metadata = metadata or {}
    sent_at = metadata.get("sent_at")
    if isinstance(sent_at, str):
      sent_at = parse_graph_datetime(sent_at)
    chunks_count = replace_knowledge_chunks(
      db,
      file_record,
      extracted_text,
      chunk_type=metadata.get("chunk_type"),
      sender=metadata.get("sender"),
      sent_at=sent_at,
      conversation_id=metadata.get("conversation_id"),
    )
    print(f"File {file_record_id} split into {chunks_count} chunks.")

    file_record.status = "completed"
    db.commit()
    print(f"Document {file_record_id} processed successfully.")

    return {"status": "success", "file": file_path, "chunks": chunks_count}

  except Exception as exc:
    print(f"Error processing document {file_record_id}: {exc}")
    traceback.print_exc()
    db.rollback()
    
    # 若此時 record 還存在 (Zip 處理失敗時可能已被刪除或還在)
    file_record = db.query(FileRecord).filter(FileRecord.id == file_record_id).first()
    if file_record:
      file_record.status = "failed"
      file_record.error_msg = str(exc)
      db.commit()

    raise self.retry(exc=exc, countdown=60)

  finally:
    db.close()


def _process_zip_contents(db, zip_record: FileRecord, zip_path: str):
    """
    解壓 ZIP 並根據內部結構建立 Folder 與 FileRecord
    """
    import zipfile
    import shutil
    from pathlib import Path
    
    temp_extract_dir = os.path.join(UPLOAD_DIR, f"temp_zip_{zip_record.id}")
    os.makedirs(temp_extract_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)
            
        # 建立目錄路徑到 Folder ID 的映射，用來處理層級結構
        # key: 相對路徑字串, value: Folder ID
        folder_map = {}
        pending_tasks = []
        
        # 遍歷解壓後的目錄
        for root, dirs, files in os.walk(temp_extract_dir):
            rel_root = os.path.relpath(root, temp_extract_dir)
            if rel_root == ".":
                current_folder_id = zip_record.folder_id
            else:
                # 確保父目錄已存在或使用 zip_record.folder_id 作為底層
                parts = Path(rel_root).parts
                parent_id = zip_record.folder_id
                
                path_acc = ""
                for part in parts:
                    path_acc = os.path.join(path_acc, part)
                    if path_acc not in folder_map:
                        # 檢查資料庫是否已有此資料夾 (同 project, 同 parent, 同 name)
                        stmt = select(Folder).where(
                            Folder.project_id == zip_record.project_id,
                            Folder.parent_id == parent_id,
                            Folder.name == part
                        )
                        folder = db.execute(stmt).scalar_one_or_none()
                        
                        if not folder:
                            folder = Folder(
                                name=part,
                                project_id=zip_record.project_id,
                                parent_id=parent_id
                            )
                            db.add(folder)
                            db.flush() # 取得 ID
                        
                        folder_map[path_acc] = folder.id
                    
                    parent_id = folder_map[path_acc]
                
                current_folder_id = parent_id

            # 處理此目錄下的檔案
            supported_exts = ["pdf", "docx", "doc", "txt", "csv", "xlsx", "xls", "odt", "mp3", "m4a", "wav", "webm", "mp4"]
            for filename in files:
                file_ext = filename.split(".")[-1].lower() if "." in filename else ""
                if file_ext not in supported_exts:
                    continue
                
                src_path = os.path.join(root, filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                dest_path = os.path.join(UPLOAD_DIR, unique_filename)
                shutil.copy2(src_path, dest_path)
                
                new_record = FileRecord(
                    filename=filename,
                    file_type=file_ext,
                    file_path=dest_path,
                    project_id=zip_record.project_id,
                    folder_id=current_folder_id,
                    status="pending",
                    source_type="zip_extracted"
                )
                db.add(new_record)
                db.flush()
                
                pending_tasks.append({
                    "file_record_id": new_record.id,
                    "file_path": dest_path
                })
        
        db.commit()
        
        # 資料庫確保已寫入後，再發送非同步解析任務
        for task_kwargs in pending_tasks:
            process_document_task.delay(**task_kwargs)
            
        print(f"Successfully unpacked ZIP {zip_record.id} and created child records.")
        
    finally:
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)


def _process_rar_contents(db, rar_record: FileRecord, rar_path: str):
    """
    解壓 RAR 並根據內部結構建立 Folder 與 FileRecord
    """
    import rarfile
    import shutil
    from pathlib import Path
    
    temp_extract_dir = os.path.join(UPLOAD_DIR, f"temp_rar_{rar_record.id}")
    os.makedirs(temp_extract_dir, exist_ok=True)
    
    try:
        with rarfile.RarFile(rar_path, 'r') as rar_ref:
            rar_ref.extractall(temp_extract_dir)
            
        # 建立目錄路徑到 Folder ID 的映射，用來處理層級結構
        # key: 相對路徑字串, value: Folder ID
        folder_map = {}
        pending_tasks = []
        
        # 遍歷解壓後的目錄
        for root, dirs, files in os.walk(temp_extract_dir):
            rel_root = os.path.relpath(root, temp_extract_dir)
            if rel_root == ".":
                current_folder_id = rar_record.folder_id
            else:
                # 確保父目錄已存在或使用 rar_record.folder_id 作為底層
                parts = Path(rel_root).parts
                parent_id = rar_record.folder_id
                
                path_acc = ""
                for part in parts:
                    path_acc = os.path.join(path_acc, part)
                    if path_acc not in folder_map:
                        # 檢查資料庫是否已有此資料夾 (同 project, 同 parent, 同 name)
                        stmt = select(Folder).where(
                            Folder.project_id == rar_record.project_id,
                            Folder.parent_id == parent_id,
                            Folder.name == part
                        )
                        folder = db.execute(stmt).scalar_one_or_none()
                        
                        if not folder:
                            folder = Folder(
                                name=part,
                                project_id=rar_record.project_id,
                                parent_id=parent_id
                            )
                            db.add(folder)
                            db.flush() # 取得 ID
                        
                        folder_map[path_acc] = folder.id
                    
                    parent_id = folder_map[path_acc]
                
                current_folder_id = parent_id

            # 處理此目錄下的檔案
            supported_exts = ["pdf", "docx", "doc", "txt", "csv", "xlsx", "xls", "odt", "mp3", "m4a", "wav", "webm", "mp4"]
            for filename in files:
                file_ext = filename.split(".")[-1].lower() if "." in filename else ""
                if file_ext not in supported_exts:
                    continue
                
                src_path = os.path.join(root, filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                dest_path = os.path.join(UPLOAD_DIR, unique_filename)
                shutil.copy2(src_path, dest_path)
                
                new_record = FileRecord(
                    filename=filename,
                    file_type=file_ext,
                    file_path=dest_path,
                    project_id=rar_record.project_id,
                    folder_id=current_folder_id,
                    status="pending",
                    source_type="rar_extracted"
                )
                db.add(new_record)
                db.flush()
                
                pending_tasks.append({
                    "file_record_id": new_record.id,
                    "file_path": dest_path
                })
        
        db.commit()
        
        # 資料庫確保已寫入後，再發送非同步解析任務
        for task_kwargs in pending_tasks:
            process_document_task.delay(**task_kwargs)
            
        print(f"Successfully unpacked RAR {rar_record.id} and created child records.")
        
    finally:
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)


@celery.task(name="sync_outlook_mailbox_task", bind=True, max_retries=2)
def sync_outlook_mailbox_task(self, mailbox_id: int, force_full_sync: bool = False):
    db = SessionLocal()
    try:
        mailbox = db.execute(
            select(OutlookMailbox).where(OutlookMailbox.id == mailbox_id)
        ).scalar_one_or_none()
        if not mailbox:
            raise ValueError(f"OutlookMailbox {mailbox_id} not found.")
        if not mailbox.is_active:
            raise ValueError(f"OutlookMailbox {mailbox_id} is inactive.")

        access_token, expires_at = ensure_valid_access_token(mailbox)
        mailbox.access_token = access_token
        mailbox.token_expires_at = expires_at
        db.commit()

        rules = db.execute(
            select(OutlookSyncRule).where(OutlookSyncRule.mailbox_id == mailbox_id)
        ).scalars().all()

        messages, delta_link = fetch_mailbox_messages(mailbox, access_token, force_full_sync)
        processed_count = 0
        deleted_count = 0
        queued_attachments = 0
        now = datetime.now(timezone.utc)

        for message in messages:
            external_message_id = message.get("id")
            if not external_message_id:
                continue

            stored_message = db.execute(
                select(OutlookMessage).where(
                    OutlookMessage.mailbox_id == mailbox_id,
                    OutlookMessage.external_message_id == external_message_id,
                )
            ).scalar_one_or_none()

            if is_removed_message(message):
                if stored_message:
                    _remove_message_artifacts(db, stored_message)
                    stored_message.is_deleted = True
                    stored_message.last_seen_at = now
                    db.commit()
                    deleted_count += 1
                continue

            target_project_id, _matched_rule = pick_target_project_id(mailbox, rules, message)
            sender = graph_sender_address(message)
            sent_at = parse_graph_datetime(message.get("sentDateTime"))
            received_at = parse_graph_datetime(message.get("receivedDateTime"))

            if not stored_message:
                stored_message = OutlookMessage(
                    mailbox_id=mailbox_id,
                    external_message_id=external_message_id,
                )
                db.add(stored_message)
                db.flush()

            stored_message.conversation_id = message.get("conversationId")
            stored_message.internet_message_id = message.get("internetMessageId")
            stored_message.subject = message.get("subject")
            stored_message.sender = sender
            stored_message.to_recipients = graph_recipient_addresses(message, "toRecipients")
            stored_message.cc_recipients = graph_recipient_addresses(message, "ccRecipients")
            stored_message.sent_at = sent_at
            stored_message.received_at = received_at
            stored_message.web_link = message.get("webLink")
            stored_message.etag = message.get("@odata.etag")
            stored_message.has_attachments = bool(message.get("hasAttachments"))
            stored_message.is_deleted = False
            stored_message.last_seen_at = now

            email_file = _upsert_email_file(db, stored_message, message, target_project_id)
            replace_knowledge_chunks(
                db,
                email_file,
                build_email_document(message),
                chunk_type="email_body",
                sender=sender,
                sent_at=sent_at,
                conversation_id=message.get("conversationId"),
            )
            email_file.status = "completed"
            email_file.error_msg = None

            attachment_jobs = []
            if message.get("hasAttachments"):
                attachments = fetch_message_attachments(access_token, external_message_id)
                for attachment in attachments:
                    if attachment.get("@odata.type") != "#microsoft.graph.fileAttachment":
                        continue
                    if attachment.get("isInline"):
                        continue

                    attachment_file = _upsert_attachment_file(
                        db,
                        message,
                        attachment,
                        target_project_id,
                        parent_file_id=email_file.id,
                    )
                    if not attachment_file:
                        continue

                    attachment_jobs.append(
                        {
                            "file_record_id": attachment_file.id,
                            "file_path": attachment_file.file_path,
                            "metadata": {
                                "chunk_type": "attachment",
                                "sender": sender,
                                "sent_at": sent_at.isoformat() if sent_at else None,
                                "conversation_id": message.get("conversationId"),
                            },
                        }
                    )

            db.commit()
            for job in attachment_jobs:
                process_document_task.delay(**job)
                queued_attachments += 1
            processed_count += 1

        mailbox.delta_link = delta_link or mailbox.delta_link
        mailbox.last_synced_at = now
        db.commit()

        return {
            "status": "success",
            "mailbox_id": mailbox_id,
            "processed_messages": processed_count,
            "deleted_messages": deleted_count,
            "queued_attachments": queued_attachments,
            "matched_rules_checked": len(rules),
        }

    except Exception as exc:
        print(f"Error syncing Outlook mailbox {mailbox_id}: {exc}")
        traceback.print_exc()
        db.rollback()
        raise self.retry(exc=exc, countdown=120)

    finally:
        db.close()


@celery.task(name="process_pst_import_task", bind=True, max_retries=1)
def process_pst_import_task(
    self,
    root_file_id: int,
    fallback_project_name: str = "Outlook Mails",
):
    db = SessionLocal()
    extracted_dir = None
    try:
        root_file = _get_file_record(db, root_file_id)
        if not root_file:
            raise ValueError(f"PST root FileRecord {root_file_id} not found.")

        if root_file.cancel_requested:
            _mark_import_cancelled(db, root_file_id)
            _delete_file_if_exists(root_file.file_path)
            return {
                "status": "cancelled",
                "root_file_id": root_file_id,
                "imported_emails": 0,
                "queued_attachments": 0,
                "failed_emails": 0,
            }

        root_file.status = "processing"
        root_file.error_msg = None
        db.commit()

        fallback_project = _ensure_project(db, fallback_project_name)
        rules = db.execute(
            select(OutlookSyncRule)
            .where(OutlookSyncRule.is_active.is_(True))
            .order_by(OutlookSyncRule.priority.asc(), OutlookSyncRule.id.asc())
        ).scalars().all()

        class FallbackMailbox:
            project_id = fallback_project.id

        mailbox = FallbackMailbox()

        for child in list(root_file.child_files or []):
            _delete_file_record(db, child)
        db.commit()

        extracted_dir = extract_pst_to_mbox_tree(root_file.file_path)
        imported_emails = 0
        queued_attachments = 0
        failed_emails = 0

        for folder_name, index, raw_message in iter_mbox_messages(extracted_dir):
            if _cancel_requested(db, root_file_id):
                root_file = _mark_import_cancelled(db, root_file_id)
                if root_file:
                    _delete_file_if_exists(root_file.file_path)
                return {
                    "status": "cancelled",
                    "root_file_id": root_file_id,
                    "imported_emails": imported_emails,
                    "queued_attachments": queued_attachments,
                    "failed_emails": failed_emails,
                }

            email_item = parse_mbox_message(folder_name, index, raw_message)
            target_project_id, _matched_rule = pick_target_project_id(
                mailbox,
                rules,
                {
                    "from": {"emailAddress": {"address": email_item.sender}},
                    "subject": email_item.subject,
                    "body": {"content": email_item.body_text},
                },
            )
            try:
                email_file = _create_pst_email_file(db, root_file, target_project_id, email_item)
                replace_knowledge_chunks(
                    db,
                    email_file,
                    build_pst_email_document(email_item),
                    chunk_type="email_body",
                    sender=email_item.sender,
                    sent_at=email_item.sent_at,
                    conversation_id=email_item.conversation_id,
                )

                attachment_jobs = []
                for attachment in email_item.attachments:
                    attachment_file = _create_pst_attachment_file(db, email_file, target_project_id, email_item, attachment)
                    if attachment_file.status != "pending":
                        continue
                    attachment_jobs.append(
                        {
                            "file_record_id": attachment_file.id,
                            "file_path": attachment_file.file_path,
                            "metadata": {
                                "chunk_type": "attachment",
                                "sender": email_item.sender,
                                "sent_at": email_item.sent_at.isoformat() if email_item.sent_at else None,
                                "conversation_id": email_item.conversation_id,
                            },
                        }
                    )

                db.commit()
                for job in attachment_jobs:
                    process_document_task.delay(**job)
                    queued_attachments += 1
                imported_emails += 1
            except Exception as email_exc:
                db.rollback()
                failed_emails += 1
                try:
                    failed_email_file = _create_pst_email_file(db, root_file, fallback_project.id, email_item)
                    failed_email_file.status = "failed"
                    failed_email_file.error_msg = str(email_exc)
                    db.commit()
                except Exception:
                    db.rollback()

        root_file.status = "completed"
        root_file.error_msg = None
        db.commit()

        # The original PST is no longer needed once all emails are split and
        # downstream attachment jobs have been queued.
        _delete_file_if_exists(root_file.file_path)

        return {
            "status": "success",
            "root_file_id": root_file_id,
            "imported_emails": imported_emails,
            "queued_attachments": queued_attachments,
            "failed_emails": failed_emails,
        }
    except Exception as exc:
        print(f"Error importing PST {root_file_id}: {exc}")
        traceback.print_exc()
        db.rollback()
        root_file = db.execute(select(FileRecord).where(FileRecord.id == root_file_id)).scalar_one_or_none()
        if root_file:
            root_file.status = "failed"
            root_file.error_msg = str(exc)
            db.commit()
        raise self.retry(exc=exc, countdown=120)
    finally:
        if extracted_dir:
            cleanup_extracted_tree(extracted_dir)
        db.close()


@celery.task(name="process_csv_import_task", bind=True, max_retries=1)
def process_csv_import_task(
    self,
    root_file_id: int,
    fallback_project_name: str = "Outlook Mails",
):
    db = SessionLocal()
    try:
        root_file = _get_file_record(db, root_file_id)
        if not root_file:
            raise ValueError(f"CSV root FileRecord {root_file_id} not found.")

        if root_file.cancel_requested:
            _mark_import_cancelled(db, root_file_id)
            _delete_file_if_exists(root_file.file_path)
            return {
                "status": "cancelled",
                "root_file_id": root_file_id,
                "imported_emails": 0,
                "queued_attachments": 0,
                "failed_emails": 0,
            }

        root_file.status = "processing"
        root_file.error_msg = None
        db.commit()

        fallback_project = _ensure_project(db, fallback_project_name)
        rules = db.execute(
            select(OutlookSyncRule)
            .where(OutlookSyncRule.is_active.is_(True))
            .order_by(OutlookSyncRule.priority.asc(), OutlookSyncRule.id.asc())
        ).scalars().all()

        class FallbackMailbox:
            project_id = fallback_project.id

        mailbox = FallbackMailbox()

        for child in list(root_file.child_files or []):
            _delete_file_record(db, child)
        db.commit()

        imported_emails = 0
        failed_emails = 0

        for email_item in iter_csv_emails(root_file.file_path):
            if _cancel_requested(db, root_file_id):
                root_file = _mark_import_cancelled(db, root_file_id)
                if root_file:
                    _delete_file_if_exists(root_file.file_path)
                return {
                    "status": "cancelled",
                    "root_file_id": root_file_id,
                    "imported_emails": imported_emails,
                    "queued_attachments": 0,
                    "failed_emails": failed_emails,
                }

            target_project_id, _matched_rule = pick_target_project_id(
                mailbox,
                rules,
                {
                    "from": {"emailAddress": {"address": email_item.sender}},
                    "subject": email_item.subject,
                    "body": {"content": email_item.body_text},
                },
            )
            try:
                email_file = _create_pst_email_file(db, root_file, target_project_id, email_item)
                replace_knowledge_chunks(
                    db,
                    email_file,
                    build_pst_email_document(email_item),
                    chunk_type="email_body",
                    sender=email_item.sender,
                    sent_at=email_item.sent_at,
                    conversation_id=email_item.conversation_id,
                )
                db.commit()
                imported_emails += 1
            except Exception as email_exc:
                db.rollback()
                failed_emails += 1
                try:
                    failed_email_file = _create_pst_email_file(db, root_file, fallback_project.id, email_item)
                    failed_email_file.status = "failed"
                    failed_email_file.error_msg = str(email_exc)
                    db.commit()
                except Exception:
                    db.rollback()

        root_file.status = "completed"
        root_file.error_msg = None
        db.commit()
        _delete_file_if_exists(root_file.file_path)

        return {
            "status": "success",
            "root_file_id": root_file_id,
            "imported_emails": imported_emails,
            "queued_attachments": 0,
            "failed_emails": failed_emails,
        }
    except Exception as exc:
        print(f"Error importing CSV {root_file_id}: {exc}")
        traceback.print_exc()
        db.rollback()
        root_file = db.execute(select(FileRecord).where(FileRecord.id == root_file_id)).scalar_one_or_none()
        if root_file:
            root_file.status = "failed"
            root_file.error_msg = str(exc)
            db.commit()
        raise self.retry(exc=exc, countdown=120)
    finally:
        db.close()
