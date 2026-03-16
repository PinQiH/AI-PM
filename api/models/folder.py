from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from api.models.base import Base, TimestampMixin

class Folder(Base, TimestampMixin):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("folders.id"), nullable=True)

    project = relationship("Project", back_populates="folders")
    parent = relationship("Folder", remote_side=[id], backref="children")
    files = relationship("FileRecord", back_populates="folder")
