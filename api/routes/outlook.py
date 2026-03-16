import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import os
import shutil

from api.core.database import SessionLocal
from api.models.file_record import FileRecord
from api.models.folder import Folder
from api.models.outlook_sync_rule import OutlookSyncRule
from api.models.project import Project
from api.schemas.outlook import (
    OutlookClassificationPreviewRequest,
    OutlookClassificationPreviewResponse,
    OutlookManualEmailSaveRequest,
    OutlookManualEmailSaveResponse,
    OutlookProcessingSummaryResponse,
    OutlookPstBatchListResponse,
    OutlookPstBatchResponse,
    OutlookPstImportResponse,
    OutlookSyncRuleCreate,
    OutlookSyncRuleResponse,
)
from api.schemas.file_record import FileRecordListResponse
from api.services.outlook import (
    build_email_document,
    email_record_filename,
    normalize_pattern,
    match_rule,
)
from api.services.ingest import replace_knowledge_chunks
from api.worker.tasks import process_csv_import_task, process_pst_import_task


router = APIRouter(prefix="/outlook", tags=["Outlook"])
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
CANCELLED_IMPORT_MESSAGE = "Import cancelled by user."
STOPPING_IMPORT_MESSAGE = "Cancellation requested by user."
ALLOWED_MATCH_TYPES = {
    "sender_contains",
    "sender_domain",
    "subject_keyword",
    "body_keyword",
    "any_keyword",
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_project(db: Session, name: str) -> Project:
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


def _ensure_mail_folder(db: Session, project_id: int) -> Folder:
    folder = db.execute(
        select(Folder).where(Folder.project_id == project_id, Folder.parent_id.is_(None), Folder.name == "mail")
    ).scalar_one_or_none()
    if folder:
        return folder

    folder = Folder(name="mail", project_id=project_id, parent_id=None)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def _ensure_global_rule_profile(db: Session, default_project_name: str = "Outlook Mails"):
    from api.models.outlook_mailbox import OutlookMailbox

    label = "__global_pst_rules__"
    existing = db.execute(select(OutlookMailbox).where(OutlookMailbox.user_email == label)).scalar_one_or_none()
    if existing:
        return existing

    default_project = _ensure_project(db, default_project_name)
    mailbox = OutlookMailbox(
        project_id=default_project.id,
        user_email=label,
        tenant_id="__manual__",
        client_id="__manual__",
        client_secret="",
        refresh_token="__manual__",
        is_active=False,
    )
    db.add(mailbox)
    db.commit()
    db.refresh(mailbox)
    return mailbox


def _get_all_active_rules(db: Session) -> list[OutlookSyncRule]:
    return db.execute(
        select(OutlookSyncRule)
        .where(OutlookSyncRule.is_active.is_(True))
        .order_by(OutlookSyncRule.priority.asc(), OutlookSyncRule.id.asc())
    ).scalars().all()


def _classify_to_project(db: Session, sender: str, subject: str, body: str) -> tuple[Project, OutlookSyncRule | None]:
    fallback_project = _ensure_project(db, "Outlook Mails")
    for rule in _get_all_active_rules(db):
        if match_rule(rule, sender=sender, subject=subject, body=body):
            target_project = db.execute(select(Project).where(Project.id == rule.target_project_id)).scalar_one_or_none()
            if target_project:
                return target_project, rule
    return fallback_project, None
@router.get("/rules", response_model=list[OutlookSyncRuleResponse])
def list_rules(db: Session = Depends(get_db)):
    _ensure_global_rule_profile(db)
    return _get_all_active_rules(db)


@router.post("/rules", response_model=OutlookSyncRuleResponse)
def create_rule(payload: OutlookSyncRuleCreate, db: Session = Depends(get_db)):
    profile = _ensure_global_rule_profile(db)
    if payload.match_type not in ALLOWED_MATCH_TYPES:
        raise HTTPException(status_code=400, detail="Invalid match_type")

    target_project = db.execute(
        select(Project).where(Project.id == payload.target_project_id)
    ).scalar_one_or_none()
    if not target_project:
        raise HTTPException(status_code=404, detail="Target project not found")

    normalized = normalize_pattern(payload.pattern)
    if not normalized:
        raise HTTPException(status_code=400, detail="Pattern cannot be empty")

    rule = OutlookSyncRule(
        mailbox_id=profile.id,
        match_type=payload.match_type,
        pattern=normalized,
        target_project_id=payload.target_project_id,
        priority=payload.priority,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    db.add(rule)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to create rule: {exc}")
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.execute(select(OutlookSyncRule).where(OutlookSyncRule.id == rule_id)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}


@router.get("/processing-summary", response_model=OutlookProcessingSummaryResponse)
def get_processing_summary(db: Session = Depends(get_db)):
    tracked_types = ("pst_archive", "csv_archive", "outlook_email", "outlook_attachment")
    processing_count = db.execute(
        select(func.count()).select_from(FileRecord).where(
            FileRecord.source_type.in_(tracked_types),
            FileRecord.status.in_(("pending", "processing")),
        )
    ).scalar_one()
    failed_count = db.execute(
        select(func.count()).select_from(FileRecord).where(
            FileRecord.source_type.in_(tracked_types),
            FileRecord.status == "failed",
        )
    ).scalar_one()
    batch_count = db.execute(
        select(func.count()).select_from(FileRecord).where(FileRecord.source_type.in_(("pst_archive", "csv_archive")))
    ).scalar_one()
    return OutlookProcessingSummaryResponse(
        processing_count=processing_count,
        failed_count=failed_count,
        batch_count=batch_count,
    )


@router.post("/pst-batches/{root_file_id}/cancel")
def cancel_pst_batch(root_file_id: int, db: Session = Depends(get_db)):
    root_record = db.execute(
        select(FileRecord).where(FileRecord.id == root_file_id, FileRecord.source_type.in_(("pst_archive", "csv_archive")))
    ).scalar_one_or_none()
    if not root_record:
        raise HTTPException(status_code=404, detail="Import batch not found")

    if root_record.status == "cancelled":
        return {
            "root_file_id": root_file_id,
            "status": "cancelled",
            "message": CANCELLED_IMPORT_MESSAGE,
        }

    if root_record.status in ("completed", "failed"):
        return {
            "root_file_id": root_file_id,
            "status": root_record.status,
            "message": f"Batch already {root_record.status}.",
        }

    root_record.cancel_requested = True
    if root_record.status == "pending":
        root_record.status = "cancelled"
        root_record.error_msg = CANCELLED_IMPORT_MESSAGE
    else:
        root_record.error_msg = STOPPING_IMPORT_MESSAGE
    db.commit()

    return {
        "root_file_id": root_file_id,
        "status": root_record.status,
        "cancel_requested": root_record.cancel_requested,
        "message": root_record.error_msg or CANCELLED_IMPORT_MESSAGE,
    }


@router.get("/pst-batches", response_model=OutlookPstBatchListResponse)
def list_pst_batches(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    total = db.execute(
        select(func.count()).select_from(FileRecord).where(FileRecord.source_type.in_(("pst_archive", "csv_archive")))
    ).scalar_one()
    records = db.execute(
        select(FileRecord)
        .where(FileRecord.source_type.in_(("pst_archive", "csv_archive")))
        .order_by(FileRecord.id.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    batch_ids = [record.id for record in records]
    count_map = {}
    if batch_ids:
        rows = db.execute(
            select(FileRecord.parent_file_id, func.count())
            .where(
                FileRecord.source_type == "outlook_email",
                FileRecord.parent_file_id.in_(batch_ids),
            )
            .group_by(FileRecord.parent_file_id)
        ).all()
        count_map = {parent_id: count for parent_id, count in rows}

    items = []
    for record in records:
        item = OutlookPstBatchResponse.model_validate(record, from_attributes=True)
        item = item.model_copy(update={"split_email_count": count_map.get(record.id, 0)})
        items.append(item)

    return OutlookPstBatchListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/pst-batches/{root_file_id}/emails", response_model=FileRecordListResponse)
def list_pst_batch_emails(
    root_file_id: int,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    root_record = db.execute(
        select(FileRecord).where(FileRecord.id == root_file_id, FileRecord.source_type.in_(("pst_archive", "csv_archive")))
    ).scalar_one_or_none()
    if not root_record:
        raise HTTPException(status_code=404, detail="Import batch not found")

    base_stmt = select(FileRecord).where(
        FileRecord.source_type == "outlook_email",
        FileRecord.parent_file_id == root_file_id,
    )
    total = db.execute(
        select(func.count()).select_from(FileRecord).where(
            FileRecord.source_type == "outlook_email",
            FileRecord.parent_file_id == root_file_id,
        )
    ).scalar_one()
    items = db.execute(
        base_stmt.order_by(FileRecord.sent_at.desc().nullslast(), FileRecord.id.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return FileRecordListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/import-pst", response_model=OutlookPstImportResponse)
async def import_pst_archive(
    file: UploadFile = File(...),
    fallback_project_name: str = Form(default="Outlook Mails"),
    db: Session = Depends(get_db),
):
    file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_ext != "pst":
        raise HTTPException(status_code=400, detail="Only .pst files are supported for this import route.")

    target_project_id = _ensure_project(db, fallback_project_name.strip() or "Outlook Mails").id
    _ensure_mail_folder(db, target_project_id)

    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    root_record = FileRecord(
        filename=file.filename,
        file_type="pst",
        file_path=file_path,
        mime_type=file.content_type or "application/vnd.ms-outlook",
        source_type="pst_archive",
        project_id=target_project_id,
        status="pending",
    )
    db.add(root_record)
    db.commit()
    db.refresh(root_record)

    task = process_pst_import_task.delay(
        root_file_id=root_record.id,
        fallback_project_name=fallback_project_name.strip() or "Outlook Mails",
    )
    return OutlookPstImportResponse(task_id=task.id, root_file_id=root_record.id, status="queued")


@router.post("/import-csv", response_model=OutlookPstImportResponse)
async def import_csv_archive(
    file: UploadFile = File(...),
    fallback_project_name: str = Form(default="Outlook Mails"),
    db: Session = Depends(get_db),
):
    file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_ext != "csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported for this import route.")

    target_project_id = _ensure_project(db, fallback_project_name.strip() or "Outlook Mails").id
    _ensure_mail_folder(db, target_project_id)

    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    root_record = FileRecord(
        filename=file.filename,
        file_type="csv",
        file_path=file_path,
        mime_type=file.content_type or "text/csv",
        source_type="csv_archive",
        project_id=target_project_id,
        status="pending",
    )
    db.add(root_record)
    db.commit()
    db.refresh(root_record)

    task = process_csv_import_task.delay(
        root_file_id=root_record.id,
        fallback_project_name=fallback_project_name.strip() or "Outlook Mails",
    )
    return OutlookPstImportResponse(task_id=task.id, root_file_id=root_record.id, status="queued")


@router.post("/classify-preview", response_model=OutlookClassificationPreviewResponse)
def classify_preview(payload: OutlookClassificationPreviewRequest, db: Session = Depends(get_db)):
    target_project, matched_rule = _classify_to_project(
        db,
        sender=payload.sender or "",
        subject=payload.subject or "",
        body=payload.body or "",
    )
    _ensure_mail_folder(db, target_project.id)

    return OutlookClassificationPreviewResponse(
        mailbox_id=0,
        matched_rule_id=matched_rule.id if matched_rule else None,
        matched_rule_type=matched_rule.match_type if matched_rule else None,
        matched_pattern=matched_rule.pattern if matched_rule else None,
        target_project_id=target_project.id,
        target_project_name=f"{target_project.name} / mail",
    )


@router.post("/manual-email", response_model=OutlookManualEmailSaveResponse)
def save_manual_email(payload: OutlookManualEmailSaveRequest, db: Session = Depends(get_db)):
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Email body cannot be empty")

    sender = (payload.sender or "").strip()
    subject = (payload.subject or "").strip() or "(No subject)"
    target_project, matched_rule = _classify_to_project(
        db,
        sender=sender,
        subject=subject,
        body=body,
    )
    mail_folder = _ensure_mail_folder(db, target_project.id)

    filename = email_record_filename(subject, datetime.now(timezone.utc), fallback_ext=".txt")
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")
    message_dict = {
        "subject": subject,
        "from": {"emailAddress": {"address": sender}},
        "toRecipients": [],
        "ccRecipients": [],
        "sentDateTime": "",
        "body": {"content": body},
    }
    with open(file_path, "w", encoding="utf-8") as fp:
        fp.write(build_email_document(message_dict))

    file_record = FileRecord(
        filename=filename,
        file_type="txt",
        file_path=file_path,
        mime_type="text/plain",
        source_type="outlook_email",
        external_id=f"manual:{uuid.uuid4().hex}",
        project_id=target_project.id,
        folder_id=mail_folder.id,
        sender=sender or None,
        status="completed",
    )
    db.add(file_record)
    db.flush()

    replace_knowledge_chunks(
        db,
        file_record,
        build_email_document(message_dict),
        chunk_type="email_body",
        sender=sender or None,
        sent_at=None,
        conversation_id=None,
    )
    db.commit()
    db.refresh(file_record)

    return OutlookManualEmailSaveResponse(
        file_id=file_record.id,
        target_project_id=target_project.id,
        target_project_name=f"{target_project.name} / mail",
        matched_rule_id=matched_rule.id if matched_rule else None,
        matched_rule_type=matched_rule.match_type if matched_rule else None,
        matched_pattern=matched_rule.pattern if matched_rule else None,
    )
