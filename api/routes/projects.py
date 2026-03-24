from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
import os

from api.core.database import SessionLocal
from api.models.project import Project
from api.models.folder import Folder
from api.models.file_record import FileRecord
from api.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["Projects"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=ProjectResponse)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db)):
    # 檢查專案是否已存在
    stmt = select(Project).where(Project.name == project_in.name)
    existing_project = db.execute(stmt).scalar_one_or_none()
    if existing_project:
        raise HTTPException(status_code=400, detail="Project with this name already exists")
    
    db_project = Project(
        name=project_in.name,
        description=project_in.description
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    stmt = select(Project)
    projects = db.execute(stmt).scalars().all()
    return projects


def _delete_file_record(record: FileRecord, db: Session):
    """刪除檔案資料列與磁碟實體檔案"""
    if record.file_path and os.path.exists(record.file_path):
        if record.source_type != "nextcloud":
            os.remove(record.file_path)
    db.delete(record)


def _delete_folder_tree(folder_id: int, folders_by_parent: dict, folder_map: dict, db: Session):
    """遞迴刪除資料夾樹（由下而上）"""
    for child in folders_by_parent.get(folder_id, []):
        _delete_folder_tree(child.id, folders_by_parent, folder_map, db)
    folder_obj = folder_map.get(folder_id)
    if folder_obj:
        db.delete(folder_obj)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """刪除專案及其所有資料夾/檔案/知識碎片"""
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1) 先刪除該專案所有檔案（包含根目錄與資料夾內）
    files = db.execute(select(FileRecord).where(FileRecord.project_id == project_id)).scalars().all()
    for file_obj in files:
        _delete_file_record(file_obj, db)

    # 2) 刪除所有資料夾（遞迴由下而上）
    folders = db.execute(select(Folder).where(Folder.project_id == project_id)).scalars().all()
    folder_map = {f.id: f for f in folders}
    folders_by_parent = {}
    root_ids = []
    for f in folders:
        if f.parent_id is None:
            root_ids.append(f.id)
        else:
            folders_by_parent.setdefault(f.parent_id, []).append(f)
    for root_id in root_ids:
        _delete_folder_tree(root_id, folders_by_parent, folder_map, db)

    # 3) 刪除專案
    db.delete(project)
    db.commit()
    return {"message": "Project and all nested resources deleted"}
