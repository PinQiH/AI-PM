"""add_outlook_sync_rules_and_mailbox_fields

Revision ID: b7d14c2f9e31
Revises: 6f9c7d2b1a44
Create Date: 2026-03-13 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d14c2f9e31"
down_revision: Union[str, None] = "6f9c7d2b1a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outlook_mailboxes", sa.Column("client_secret", sa.Text(), nullable=True))
    op.add_column("outlook_mailboxes", sa.Column("source_folder_id", sa.String(), nullable=True))

    op.create_table(
        "outlook_sync_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mailbox_id", sa.Integer(), nullable=False),
        sa.Column("match_type", sa.String(), nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("target_project_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["mailbox_id"], ["outlook_mailboxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mailbox_id", "match_type", "pattern", name="uq_outlook_sync_rules_unique_pattern"),
    )
    op.create_index("ix_outlook_sync_rules_id", "outlook_sync_rules", ["id"], unique=False)
    op.create_index("ix_outlook_sync_rules_mailbox_id", "outlook_sync_rules", ["mailbox_id"], unique=False)
    op.create_index("ix_outlook_sync_rules_target_project_id", "outlook_sync_rules", ["target_project_id"], unique=False)
    op.alter_column("outlook_sync_rules", "priority", server_default=None)
    op.alter_column("outlook_sync_rules", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_outlook_sync_rules_target_project_id", table_name="outlook_sync_rules")
    op.drop_index("ix_outlook_sync_rules_mailbox_id", table_name="outlook_sync_rules")
    op.drop_index("ix_outlook_sync_rules_id", table_name="outlook_sync_rules")
    op.drop_table("outlook_sync_rules")

    op.drop_column("outlook_mailboxes", "source_folder_id")
    op.drop_column("outlook_mailboxes", "client_secret")
