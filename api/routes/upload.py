from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Optional, List
import os
import shutil
import uuid
import mimetypes

from api.core.database import SessionLocal
from api.models.file_record import FileRecord
from api.models.folder import Folder
from api.models.knowledge import KnowledgeBase
from api.schemas.file_record import FileRecordResponse, FileUpdateRequest, FileRecordListResponse
from api.worker.tasks import process_document_task

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()


def _delete_file_record_tree(record: FileRecord, db: Session):
  for child in list(record.child_files or []):
    _delete_file_record_tree(child, db)
  if os.path.exists(record.file_path):
    os.remove(record.file_path)
  db.delete(record)

@router.post("", response_model=FileRecordResponse)
async def upload_file(
  file: UploadFile = File(...),
  project_id: int = Form(...),
  folder_id: Optional[int] = Form(None),
  db: Session = Depends(get_db)
):
  # 1. 儲存檔案
  file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
  unique_filename = f"{uuid.uuid4()}_{file.filename}"
  file_path = os.path.join(UPLOAD_DIR, unique_filename)

  with open(file_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)

  # 2. 建立 FileRecord
  db_file_record = FileRecord(
    filename=file.filename,
    file_type=file_ext,
    file_path=file_path,
    mime_type=file.content_type,
    source_type="upload",
    project_id=project_id,
    folder_id=folder_id,
    status="pending"
  )
  db.add(db_file_record)
  db.commit()
  db.refresh(db_file_record)

  # 3. 發送 Celery 任務進行背景處理 (Early Return)
  process_document_task.delay(file_record_id=db_file_record.id, file_path=file_path)

  return db_file_record


@router.get("", response_model=List[FileRecordResponse])
def list_files(
  project_id: Optional[int] = None,
  db: Session = Depends(get_db)
):
  """列出所有 FileRecord，可依 project_id 過濾"""
  stmt = select(FileRecord)
  if project_id:
    stmt = stmt.where(FileRecord.project_id == project_id)
  stmt = stmt.order_by(FileRecord.id.desc())
  records = db.execute(stmt).scalars().all()
  return records


@router.get("/paged", response_model=FileRecordListResponse)
def list_files_paged(
  project_id: Optional[int] = None,
  folder_id: Optional[int] = None,
  status: Optional[str] = None,
  source_type: Optional[str] = None,
  limit: int = 50,
  offset: int = 0,
  db: Session = Depends(get_db)
):
  """分頁列出 FileRecord，避免一次載入過多資料"""
  limit = max(1, min(limit, 200))
  offset = max(0, offset)

  filters = []
  if project_id:
    filters.append(FileRecord.project_id == project_id)
  if folder_id is not None:
    if folder_id == -1:
      filters.append(FileRecord.folder_id.is_(None))
    else:
      filters.append(FileRecord.folder_id == folder_id)
  if status:
    filters.append(FileRecord.status == status)
  if source_type:
    filters.append(FileRecord.source_type == source_type)

  stmt = select(FileRecord)
  count_stmt = select(func.count()).select_from(FileRecord)
  for condition in filters:
    stmt = stmt.where(condition)
    count_stmt = count_stmt.where(condition)

  stmt = stmt.order_by(FileRecord.id.desc()).offset(offset).limit(limit)
  total = db.execute(count_stmt).scalar_one()
  records = db.execute(stmt).scalars().all()
  return FileRecordListResponse(items=records, total=total, limit=limit, offset=offset)


@router.get("/{file_id}", response_model=FileRecordResponse)
def get_file(file_id: int, db: Session = Depends(get_db)):
  stmt = select(FileRecord).where(FileRecord.id == file_id)
  record = db.execute(stmt).scalar_one_or_none()
  if not record:
    raise HTTPException(status_code=404, detail="File record not found")
  return record


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db)):
  """刪除指定 FileRecord 及其所有知識碎片，並移除磁碟上的實體檔案"""
  stmt = select(FileRecord).where(FileRecord.id == file_id)
  record = db.execute(stmt).scalar_one_or_none()

  if not record:
    raise HTTPException(status_code=404, detail="File not found")

  _delete_file_record_tree(record, db)
  db.commit()


@router.patch("/{file_id}", response_model=FileRecordResponse)
def update_file(
  file_id: int,
  update_in: FileUpdateRequest,
  db: Session = Depends(get_db)
):
  """更新檔案資訊：支援改檔名與移動資料夾"""
  stmt = select(FileRecord).where(FileRecord.id == file_id)
  record = db.execute(stmt).scalar_one_or_none()
  if not record:
    raise HTTPException(status_code=404, detail="File not found")

  has_filename = "filename" in update_in.model_fields_set
  has_folder = "folder_id" in update_in.model_fields_set
  if not has_filename and not has_folder:
    raise HTTPException(status_code=400, detail="No update fields provided")

  if has_filename:
    if update_in.filename is None:
      raise HTTPException(status_code=400, detail="Filename cannot be null")
    old_root, old_ext = os.path.splitext(record.filename)
    new_root, new_ext = os.path.splitext(update_in.filename.strip())

    if not new_root:
      raise HTTPException(status_code=400, detail="Filename cannot be empty")

    if old_ext.lower() != new_ext.lower():
      raise HTTPException(status_code=400, detail="File extension cannot be changed")

    record.filename = f"{new_root}{old_ext}"

  if has_folder:
    if update_in.folder_id in (-1, None):
      record.folder_id = None
    else:
      stmt_folder = select(Folder).where(Folder.id == update_in.folder_id)
      target_folder = db.execute(stmt_folder).scalar_one_or_none()
      if not target_folder:
        raise HTTPException(status_code=404, detail="Target folder not found")
      if target_folder.project_id != record.project_id:
        raise HTTPException(status_code=400, detail="Target folder belongs to different project")
      record.folder_id = update_in.folder_id

  db.commit()
  db.refresh(record)
  return record

@router.get("/{file_id}/preview")
def get_file_preview(file_id: int, db: Session = Depends(get_db)):
    """取得檔案的知識片段預覽"""
    # 1. 確認檔案存在
    stmt = select(FileRecord).where(FileRecord.id == file_id)
    record = db.execute(stmt).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="File record not found")

    if record.status != "completed":
        return {"preview": f"檔案狀態為 {record.status}，尚無預覽內容。"}

    # 2. 取得第一個知識片段
    kb_stmt = select(KnowledgeBase).where(KnowledgeBase.file_id == file_id).limit(1)
    kb_content = db.execute(kb_stmt).scalar_one_or_none()
    
    if not kb_content:
        return {"preview": "此檔案已完成處理，但未產生任何知識片段。"}

    return {"preview": kb_content.content}

@router.get("/{file_id}/download")
def get_file_download(
    file_id: int,
    preview: bool = False,
    as_attachment: bool = False,
    db: Session = Depends(get_db),
):
    """下載/獲取原始檔案，支援 Word 轉 HTML 預覽"""
    stmt = select(FileRecord).where(FileRecord.id == file_id)
    record = db.execute(stmt).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="File record not found")
    
    if not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Physical file not found on disk")
    
    # 針對 Word 檔案的特殊預覽處理
    if preview and record.file_type.lower() == "docx":
        try:
            import mammoth
            with open(record.file_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = f"""
                <html>
                <head><meta charset="utf-8"><style>body{{font-family:sans-serif;line-height:1.6;padding:20px;}}</style></head>
                <body>{result.value}</body>
                </html>
                """
                from fastapi import Response
                return Response(content=html, media_type="text/html")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Word conversion failed: {str(e)}")

    # 動態識別 MIME 類型
    mime_type, _ = mimetypes.guess_type(record.file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
        
    disposition = "attachment" if as_attachment else "inline"
    return FileResponse(
        path=record.file_path,
        filename=record.filename,
        media_type=mime_type,
        content_disposition_type=disposition,
    )
