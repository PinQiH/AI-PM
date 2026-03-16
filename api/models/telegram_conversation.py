from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, TimestampMixin


class TelegramConversation(Base, TimestampMixin):
    __tablename__ = "telegram_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    awaiting_scope_choice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    awaiting_project_choice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected_project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    selected_project_name: Mapped[str] = mapped_column(String, nullable=False, default="全部專案")
    last_user_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    selected_project = relationship("Project")
    messages = relationship(
        "TelegramMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="TelegramMessage.created_at.asc()",
    )
