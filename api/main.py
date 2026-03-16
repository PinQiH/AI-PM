from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.routes import admin, projects, folders, upload, query, outlook

app = FastAPI(title="ElenB API", description="AI Agent for PM Knowledge Base", version="0.1.0")

# 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生產環境中應具體指定來源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(folders.router)
app.include_router(upload.router)
app.include_router(query.router)
app.include_router(outlook.router)
app.include_router(admin.router)

class HealthCheck(BaseModel):
    status: str = "OK"

@app.get("/health", response_model=HealthCheck, tags=["System"])
def health_check():
    """
    檢查 API 服務是否正常運作
    """
    return HealthCheck(status="OK")
