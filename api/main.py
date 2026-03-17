from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from api.routes import admin, projects, folders, upload, query, outlook

app = FastAPI(title="ElenB API", description="AI Agent for PM Knowledge Base", version="0.1.0")
API_PREFIX = "/api"


def _get_allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ]

# 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(folders.router, prefix=API_PREFIX)
app.include_router(upload.router, prefix=API_PREFIX)
app.include_router(query.router, prefix=API_PREFIX)
app.include_router(outlook.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)

class HealthCheck(BaseModel):
    status: str = "OK"

@app.get(f"{API_PREFIX}/health", response_model=HealthCheck, tags=["System"])
def health_check():
    """
    檢查 API 服務是否正常運作
    """
    return HealthCheck(status="OK")
