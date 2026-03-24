import os
import mimetypes
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from api.core.database import SessionLocal
from api.models.file_record import FileRecord
from api.models.folder import Folder
from api.worker.tasks import process_document_task

router = APIRouter(prefix="/nextcloud", tags=["Nextcloud"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

NEXTCLOUD_ROOT = "/nextcloud"

class NextcloudImportRequest(BaseModel):
    project_id: int
    folder_id: Optional[int] = None
    path: str

class NextcloudListItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None

class NextcloudListResponse(BaseModel):
    current_path: str
    items: List[NextcloudListItem]

@router.get("/list", response_model=NextcloudListResponse)
def list_nextcloud_directory(path: str = NEXTCLOUD_ROOT):
    """回傳指定 Nextcloud 路徑下的實體檔案與資料夾清單"""
    if not path.startswith(NEXTCLOUD_ROOT):
        raise HTTPException(status_code=400, detail="Invalid path, must start with /nextcloud")
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Path not found")
        
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Path is not a directory")
        
    items = []
    try:
        for entry in os.scandir(path):
            items.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    # 以資料夾優先，再來按名稱排序
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return {"current_path": path, "items": items}

@router.get("/download")
def preview_nextcloud_file(path: str):
    """供前端在匯入前，直接預覽 Nextcloud 的實體檔案"""
    if not path.startswith(NEXTCLOUD_ROOT):
        raise HTTPException(status_code=400, detail="Invalid path")
        
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
        
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "application/octet-stream"
        
    return FileResponse(
        path=path,
        filename=os.path.basename(path),
        media_type=mime_type,
        content_disposition_type="inline"
    )

@router.post("/import")
def import_from_nextcloud(req: NextcloudImportRequest, db: Session = Depends(get_db)):
    """匯入 Nextcloud 單一檔案或整個資料夾"""
    if not req.path.startswith(NEXTCLOUD_ROOT):
        raise HTTPException(status_code=400, detail="Invalid path")
        
    if not os.path.exists(req.path):
        raise HTTPException(status_code=404, detail="Path not found")
        
    supported_exts = ["pdf", "docx", "doc", "txt", "csv", "xlsx", "xls", "odt", "zip", "rar", "mp3", "m4a", "wav", "webm", "mp4"]
    
    tasks_queued = 0
    
    def _create_record(file_path: str, current_folder_id: Optional[int]):
        filename = os.path.basename(file_path)
        file_ext = filename.split(".")[-1].lower() if "." in filename else ""
        if file_ext not in supported_exts:
            return 0
            
        stmt = select(FileRecord).where(
            FileRecord.file_path == file_path,
            FileRecord.project_id == req.project_id
        )
        existing = db.execute(stmt).scalar_one_or_none()
        if existing:
            return 0
            
        mime_type, _ = mimetypes.guess_type(file_path)
        record = FileRecord(
            filename=filename,
            file_type=file_ext,
            file_path=file_path,
            mime_type=mime_type or "application/octet-stream",
            source_type="nextcloud",
            project_id=req.project_id,
            folder_id=current_folder_id,
            status="pending"
        )
        db.add(record)
        db.flush()
        process_document_task.delay(file_record_id=record.id, file_path=record.file_path)
        return 1

    if os.path.isfile(req.path):
        tasks_queued += _create_record(req.path, req.folder_id)
        db.commit()
        return {"status": "success", "imported_files": tasks_queued, "message": "File queued for import"}
        
    elif os.path.isdir(req.path):
        top_folder_name = os.path.basename(req.path.rstrip('/\\'))
        if top_folder_name:
            stmt = select(Folder).where(
                Folder.project_id == req.project_id,
                Folder.parent_id == req.folder_id,
                Folder.name == top_folder_name
            )
            top_folder = db.execute(stmt).scalar_one_or_none()
            if not top_folder:
                top_folder = Folder(
                    name=top_folder_name,
                    project_id=req.project_id,
                    parent_id=req.folder_id
                )
                db.add(top_folder)
                db.flush()
            folder_map = {req.path: top_folder.id}
        else:
            folder_map = {req.path: req.folder_id}
        
        for root, dirs, files in os.walk(req.path):
            parent_id = folder_map.get(root)
            
            for d in dirs:
                dir_path = os.path.join(root, d)
                stmt = select(Folder).where(
                    Folder.project_id == req.project_id,
                    Folder.parent_id == parent_id,
                    Folder.name == d
                )
                folder = db.execute(stmt).scalar_one_or_none()
                if not folder:
                    folder = Folder(
                        name=d,
                        project_id=req.project_id,
                        parent_id=parent_id
                    )
                    db.add(folder)
                    db.flush()
                folder_map[dir_path] = folder.id
                
            for f in files:
                file_path = os.path.join(root, f)
                tasks_queued += _create_record(file_path, parent_id)
                
        db.commit()
        msg = f"Directory scan complete. {tasks_queued} files queued for import."
        return {"status": "success", "imported_files": tasks_queued, "message": msg}
        
    return {"status": "error", "message": "Unknown path type"}
