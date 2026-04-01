import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 資料庫設定
    PROJECT_NAME: str = "ElenB"
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "admin")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "admin")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "project_brain")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "db")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        # 如果有設定 DATABASE_URL 優先使用，否則組合參數
        return os.getenv("DATABASE_URL", f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}")

    # OpenAI 設定
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # 地端 LLM 設定 (例如 Ollama)
    USE_LOCAL_LLM: bool = os.getenv("USE_LOCAL_LLM", "False").lower() == "true"
    LOCAL_LLM_URL: str = os.getenv(
        "LOCAL_LLM_URL", "http://192.168.12.111:11434/api/chat")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen3-coder-next")
    LOCAL_LLM_EMBEDDING_URL: str = os.getenv(
        "LOCAL_LLM_EMBEDDING_URL", "http://192.168.12.111:11434/api/embeddings")
    LOCAL_LLM_EMBEDDING_MODEL: str = os.getenv(
        "LOCAL_LLM_EMBEDDING_MODEL", "nomic-embed-text")
    LOCAL_LLM_EMBEDDING_DIM: int = 768
    LOCAL_WHISPER_URL: str = os.getenv(
        "LOCAL_WHISPER_URL", "http://192.168.12.111:8001/transcribe")


    # Telegram 設定
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    TELEGRAM_DEFAULT_PROJECT_ID: str = os.getenv(
        "TELEGRAM_DEFAULT_PROJECT_ID", "")
    PUBLIC_API_BASE_URL: str = os.getenv(
        "PUBLIC_API_BASE_URL", "http://localhost:8000")
    
    @property
    def PUBLIC_API_URL(self) -> str:
        """取得外部可存取的完整 API 基礎 URL (不含末尾斜槓)"""
        return self.PUBLIC_API_BASE_URL.rstrip("/")

    TELEGRAM_IDLE_TIMEOUT_MINUTES: str = os.getenv(
        "TELEGRAM_IDLE_TIMEOUT_MINUTES", "30")

    # Outlook / Microsoft Graph
    OUTLOOK_GRAPH_BASE_URL: str = os.getenv(
        "OUTLOOK_GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0")
    OUTLOOK_OAUTH_SCOPE: str = os.getenv(
        "OUTLOOK_OAUTH_SCOPE", "offline_access Mail.Read User.Read")
    OUTLOOK_SYNC_PAGE_SIZE: int = int(
        os.getenv("OUTLOOK_SYNC_PAGE_SIZE", "25"))
    OUTLOOK_APP_TENANT_ID: str = os.getenv("OUTLOOK_APP_TENANT_ID", "")
    OUTLOOK_APP_CLIENT_ID: str = os.getenv("OUTLOOK_APP_CLIENT_ID", "")
    OUTLOOK_APP_CLIENT_SECRET: str = os.getenv("OUTLOOK_APP_CLIENT_SECRET", "")
    PUBLIC_WEB_BASE_URL: str = os.getenv(
        "PUBLIC_WEB_BASE_URL", "http://localhost:8501")

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=".env", extra='ignore')


settings = Settings()
