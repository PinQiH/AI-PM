from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from api.models.base import Base, TimestampMixin

class FileRecord(Base, TimestampMixin):
    __tablename__ = "file_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False) # e.g., 'pdf', 'mp3', 'docx'
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="upload")
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    parent_file_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("file_records.id", ondelete="CASCADE"), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    md5_hash: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending") # pending, processing, completed, failed, cancelled
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_msg: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    folder_id: Mapped[int] = mapped_column(Integer, ForeignKey("folders.id"), nullable=True)
    
    project = relationship("Project", back_populates="files")
    folder = relationship("Folder", back_populates="files")
    knowledge_fragments = relationship("KnowledgeBase", back_populates="source_file", cascade="all, delete-orphan")
    linked_outlook_messages = relationship("OutlookMessage", back_populates="email_file")
    parent_file = relationship("FileRecord", remote_side=[id], back_populates="child_files")
    child_files = relationship("FileRecord", back_populates="parent_file", cascade="all, delete-orphan")
