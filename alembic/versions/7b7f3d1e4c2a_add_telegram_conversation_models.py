"""add_telegram_conversation_models

Revision ID: 7b7f3d1e4c2a
Revises: 6f9c7d2b1a44
Create Date: 2026-03-13 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b7f3d1e4c2a"
down_revision: Union[str, None] = "6f9c7d2b1a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("awaiting_scope_choice", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("awaiting_project_choice", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("selected_project_id", sa.Integer(), nullable=True),
        sa.Column("selected_project_name", sa.String(), nullable=False, server_default="全部專案"),
        sa.Column("last_user_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["selected_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index("ix_telegram_conversations_id", "telegram_conversations", ["id"], unique=False)
    op.alter_column("telegram_conversations", "awaiting_scope_choice", server_default=None)
    op.alter_column("telegram_conversations", "awaiting_project_choice", server_default=None)
    op.alter_column("telegram_conversations", "selected_project_name", server_default=None)
    op.alter_column("telegram_conversations", "idle_notified", server_default=None)

    op.create_table(
        "telegram_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["telegram_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_messages_id", "telegram_messages", ["id"], unique=False)
    op.create_index("ix_telegram_messages_conversation_id", "telegram_messages", ["conversation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_telegram_messages_conversation_id", table_name="telegram_messages")
    op.drop_index("ix_telegram_messages_id", table_name="telegram_messages")
    op.drop_table("telegram_messages")

    op.drop_index("ix_telegram_conversations_id", table_name="telegram_conversations")
    op.drop_table("telegram_conversations")
