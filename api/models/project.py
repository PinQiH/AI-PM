from sqlalchemy import String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.models.base import Base, TimestampMixin

class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    folders = relationship("Folder", back_populates="project", cascade="all, delete-orphan")
    files = relationship("FileRecord", back_populates="project", cascade="all, delete-orphan")
    outlook_mailbox = relationship("OutlookMailbox", back_populates="project", uselist=False, cascade="all, delete-orphan")
    outlook_sync_rules = relationship("OutlookSyncRule", back_populates="target_project")
