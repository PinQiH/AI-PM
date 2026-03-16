from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, TimestampMixin


class OutlookMessage(Base, TimestampMixin):
    __tablename__ = "outlook_messages"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "external_message_id", name="uq_outlook_messages_mailbox_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mailbox_id: Mapped[int] = mapped_column(Integer, ForeignKey("outlook_mailboxes.id", ondelete="CASCADE"), nullable=False)
    email_file_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("file_records.id", ondelete="SET NULL"), nullable=True)

    external_message_id: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    internet_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_recipients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cc_recipients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    web_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    etag: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    mailbox = relationship("OutlookMailbox", back_populates="messages")
    email_file = relationship("FileRecord", back_populates="linked_outlook_messages")
