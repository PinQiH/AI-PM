from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
import os

from api.core.database import SessionLocal
from api.models.folder import Folder
from api.models.project import Project
from api.models.file_record import FileRecord
from api.schemas.folder import FolderCreate, FolderResponse

router = APIRouter(prefix="/folders", tags=["Folders"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=FolderResponse)
def create_folder(folder_in: FolderCreate, db: Session = Depends(get_db)):
    # 確認 project 是否存在
    stmt_proj = select(Project).where(Project.id == folder_in.project_id)
    project = db.execute(stmt_proj).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 若有 parent_id，確認 parent 是否存在且屬於同一個 project
    if folder_in.parent_id:
        stmt_parent = select(Folder).where(Folder.id == folder_in.parent_id)
        parent = db.execute(stmt_parent).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if parent.project_id != folder_in.project_id:
            raise HTTPException(status_code=400, detail="Parent folder belongs to a different project")

    db_folder = Folder(
        name=folder_in.name,
        project_id=folder_in.project_id,
        parent_id=folder_in.parent_id
    )
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return db_folder

@router.get("", response_model=List[FolderResponse])
def list_folders(project_id: int, db: Session = Depends(get_db)):
    stmt = select(Folder).where(Folder.project_id == project_id)
    folders = db.execute(stmt).scalars().all()
    return folders


@router.delete("/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    """刪除指定資料夾及其所有子資料夾與檔案"""
    target = db.execute(select(Folder).where(Folder.id == folder_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Folder not found")

    all_folders = db.execute(select(Folder).where(Folder.project_id == target.project_id)).scalars().all()
    folder_map = {f.id: f for f in all_folders}
    children_map = {}
    for f in all_folders:
        if f.parent_id:
            children_map.setdefault(f.parent_id, []).append(f.id)

    # 收集要刪除的資料夾 id（含子孫）
    to_delete_ids = []
    stack = [folder_id]
    while stack:
        current = stack.pop()
        to_delete_ids.append(current)
        stack.extend(children_map.get(current, []))

    # 先刪檔案與實體檔
    files = db.execute(select(FileRecord).where(FileRecord.folder_id.in_(to_delete_ids))).scalars().all()
    for file_obj in files:
        if file_obj.file_path and os.path.exists(file_obj.file_path):
            os.remove(file_obj.file_path)
        db.delete(file_obj)

    # 再刪資料夾（深度優先：子 -> 父）
    for fid in reversed(to_delete_ids):
        folder_obj = folder_map.get(fid)
        if folder_obj:
            db.delete(folder_obj)

    db.commit()
    return {"message": "Folder and all nested resources deleted"}
