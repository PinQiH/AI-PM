import os
from celery import Celery

# 取得 Redis Broker URL, 預設為 localhost 若環境變數未設定
redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# 初始化 Celery 應用程式
celery = Celery(
    "elenb_tasks",
    broker=redis_url,
    backend=redis_url,
    include=["api.worker.tasks"] # 預留，未來放真實任務的模組
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,
)

@celery.task(name="dummy_task")
def dummy_task(message: str):
    """
    一個測試用的 Celery 任務
    """
    print(f"Executing dummy task with message: {message}")
    return f"Processed: {message}"
