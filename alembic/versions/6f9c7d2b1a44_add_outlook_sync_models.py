"""add_outlook_sync_models

Revision ID: 6f9c7d2b1a44
Revises: 598a0c6a49e2
Create Date: 2026-03-12 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f9c7d2b1a44"
down_revision: Union[str, None] = "598a0c6a49e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("file_records", sa.Column("mime_type", sa.String(), nullable=True))
    op.add_column("file_records", sa.Column("source_type", sa.String(), nullable=False, server_default="upload"))
    op.add_column("file_records", sa.Column("external_id", sa.String(), nullable=True))
    op.create_index("ix_file_records_source_type", "file_records", ["source_type"], unique=False)
    op.create_index("ix_file_records_external_id", "file_records", ["external_id"], unique=False)
    op.alter_column("file_records", "source_type", server_default=None)

    op.add_column("knowledge_base", sa.Column("chunk_type", sa.String(), nullable=True))
    op.add_column("knowledge_base", sa.Column("sender", sa.String(), nullable=True))
    op.add_column("knowledge_base", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_base", sa.Column("conversation_id", sa.String(), nullable=True))
    op.create_index("ix_knowledge_base_sent_at", "knowledge_base", ["sent_at"], unique=False)
    op.create_index("ix_knowledge_base_conversation_id", "knowledge_base", ["conversation_id"], unique=False)

    op.create_table(
        "outlook_mailboxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delta_link", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index("ix_outlook_mailboxes_id", "outlook_mailboxes", ["id"], unique=False)
    op.alter_column("outlook_mailboxes", "is_active", server_default=None)

    op.create_table(
        "outlook_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mailbox_id", sa.Integer(), nullable=False),
        sa.Column("email_file_id", sa.Integer(), nullable=True),
        sa.Column("external_message_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("internet_message_id", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("sender", sa.String(), nullable=True),
        sa.Column("to_recipients", sa.Text(), nullable=True),
        sa.Column("cc_recipients", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("web_link", sa.Text(), nullable=True),
        sa.Column("etag", sa.String(), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["email_file_id"], ["file_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mailbox_id"], ["outlook_mailboxes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mailbox_id", "external_message_id", name="uq_outlook_messages_mailbox_external"),
    )
    op.create_index("ix_outlook_messages_id", "outlook_messages", ["id"], unique=False)
    op.create_index("ix_outlook_messages_conversation_id", "outlook_messages", ["conversation_id"], unique=False)
    op.create_index("ix_outlook_messages_sent_at", "outlook_messages", ["sent_at"], unique=False)
    op.alter_column("outlook_messages", "has_attachments", server_default=None)
    op.alter_column("outlook_messages", "is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_outlook_messages_sent_at", table_name="outlook_messages")
    op.drop_index("ix_outlook_messages_conversation_id", table_name="outlook_messages")
    op.drop_index("ix_outlook_messages_id", table_name="outlook_messages")
    op.drop_table("outlook_messages")

    op.drop_index("ix_outlook_mailboxes_id", table_name="outlook_mailboxes")
    op.drop_table("outlook_mailboxes")

    op.drop_index("ix_knowledge_base_conversation_id", table_name="knowledge_base")
    op.drop_index("ix_knowledge_base_sent_at", table_name="knowledge_base")
    op.drop_column("knowledge_base", "conversation_id")
    op.drop_column("knowledge_base", "sent_at")
    op.drop_column("knowledge_base", "sender")
    op.drop_column("knowledge_base", "chunk_type")

    op.drop_index("ix_file_records_external_id", table_name="file_records")
    op.drop_index("ix_file_records_source_type", table_name="file_records")
    op.drop_column("file_records", "external_id")
    op.drop_column("file_records", "source_type")
    op.drop_column("file_records", "mime_type")
