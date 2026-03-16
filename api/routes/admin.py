from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from api.core.config import settings
from api.core.database import SessionLocal
from api.models.file_record import FileRecord
from api.models.project import Project


router = APIRouter(prefix="/admin", tags=["Admin"])

APP_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = APP_ROOT / "uploads"
ENV_FILE = APP_ROOT / ".env"


class AdminSummaryResponse(BaseModel):
    project_count: int
    file_count: int
    completed_count: int
    pending_count: int
    failed_count: int


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _cleanup_path(path: str):
    shutil.rmtree(path, ignore_errors=True)


def _build_backup_archive() -> tuple[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    temp_dir = tempfile.mkdtemp(prefix="elenb_backup_")
    temp_path = Path(temp_dir)

    if not ENV_FILE.exists():
        raise HTTPException(status_code=404, detail=".env file not found")

    db_url = make_url(settings.SQLALCHEMY_DATABASE_URI)
    db_name = db_url.database
    db_host = db_url.host
    db_port = str(db_url.port or 5432)
    db_user = db_url.username
    db_password = db_url.password

    if not all([db_name, db_host, db_user]):
        raise HTTPException(status_code=500, detail="Database connection settings are incomplete")

    dump_name = f"postgres_{db_name}_{timestamp}.sql"
    dump_path = temp_path / dump_name
    uploads_name = f"uploads_{timestamp}.tar.gz"
    uploads_path = temp_path / uploads_name
    env_name = f"env_{timestamp}.env"
    env_path = temp_path / env_name
    archive_name = f"elenb_backup_{timestamp}.zip"
    archive_path = temp_path / archive_name

    dump_env = os.environ.copy()
    if db_password:
        dump_env["PGPASSWORD"] = db_password

    dump_cmd = [
        "pg_dump",
        "--host",
        db_host,
        "--port",
        db_port,
        "--username",
        db_user,
        "--dbname",
        db_name,
        "--file",
        str(dump_path),
    ]

    try:
        subprocess.run(
            dump_cmd,
            check=True,
            capture_output=True,
            text=True,
            env=dump_env,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="pg_dump is not installed in the API container") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "pg_dump failed"
        raise HTTPException(status_code=500, detail=f"Failed to create PostgreSQL dump: {detail}") from exc

    with tarfile.open(uploads_path, "w:gz") as tar:
        if UPLOADS_DIR.exists():
            tar.add(UPLOADS_DIR, arcname="uploads")
        else:
            empty_dir = temp_path / "uploads"
            empty_dir.mkdir(exist_ok=True)
            tar.add(empty_dir, arcname="uploads")

    shutil.copy2(ENV_FILE, env_path)

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(dump_path, arcname=dump_name)
        archive.write(uploads_path, arcname=uploads_name)
        archive.write(env_path, arcname=env_name)

    return temp_dir, str(archive_path)


@router.get("/summary", response_model=AdminSummaryResponse)
def get_admin_summary(db: Session = Depends(get_db)):
    project_count = db.execute(select(func.count()).select_from(Project)).scalar_one()
    file_count = db.execute(select(func.count()).select_from(FileRecord)).scalar_one()
    completed_count = db.execute(
        select(func.count()).select_from(FileRecord).where(FileRecord.status == "completed")
    ).scalar_one()
    pending_count = db.execute(
        select(func.count()).select_from(FileRecord).where(FileRecord.status.in_(("pending", "processing")))
    ).scalar_one()
    failed_count = db.execute(
        select(func.count()).select_from(FileRecord).where(FileRecord.status == "failed")
    ).scalar_one()
    return AdminSummaryResponse(
        project_count=project_count,
        file_count=file_count,
        completed_count=completed_count,
        pending_count=pending_count,
        failed_count=failed_count,
    )


@router.get("/backup")
def download_backup(background_tasks: BackgroundTasks):
    temp_dir, archive_path = _build_backup_archive()
    background_tasks.add_task(_cleanup_path, temp_dir)
    return FileResponse(
        path=archive_path,
        filename=Path(archive_path).name,
        media_type="application/zip",
    )
