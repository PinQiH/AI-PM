from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, TimestampMixin


class OutlookSyncRule(Base, TimestampMixin):
    __tablename__ = "outlook_sync_rules"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "match_type", "pattern", name="uq_outlook_sync_rules_unique_pattern"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mailbox_id: Mapped[int] = mapped_column(Integer, ForeignKey("outlook_mailboxes.id", ondelete="CASCADE"), nullable=False)
    match_type: Mapped[str] = mapped_column(String, nullable=False)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    target_project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    mailbox = relationship("OutlookMailbox", back_populates="rules")
    target_project = relationship("Project", back_populates="outlook_sync_rules")
