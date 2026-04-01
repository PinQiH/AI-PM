from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from api.models.base import Base, TimestampMixin

class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_records.id", ondelete="CASCADE"), nullable=True) # 可以對應到原始檔案
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # 根據是否使用地端模型自動切換維度 (OpenAI=1536, Local=依設定)
    from api.core.config import settings
    embedding = mapped_column(Vector(settings.LOCAL_LLM_EMBEDDING_DIM if settings.USE_LOCAL_LLM else 1536))
    
    source_file = relationship("FileRecord", back_populates="knowledge_fragments")
