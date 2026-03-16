"""add_file_record_parent_and_email_meta

Revision ID: d4f2a7c8b9e1
Revises: a1e6c9d4b2f0
Create Date: 2026-03-13 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f2a7c8b9e1"
down_revision: Union[str, None] = "a1e6c9d4b2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("file_records", sa.Column("parent_file_id", sa.Integer(), nullable=True))
    op.add_column("file_records", sa.Column("sender", sa.String(), nullable=True))
    op.add_column("file_records", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("file_records", sa.Column("conversation_id", sa.String(), nullable=True))
    op.create_index("ix_file_records_parent_file_id", "file_records", ["parent_file_id"], unique=False)
    op.create_index("ix_file_records_conversation_id", "file_records", ["conversation_id"], unique=False)
    op.create_index("ix_file_records_sent_at", "file_records", ["sent_at"], unique=False)
    op.create_foreign_key(
        "fk_file_records_parent_file_id",
        "file_records",
        "file_records",
        ["parent_file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_file_records_parent_file_id", "file_records", type_="foreignkey")
    op.drop_index("ix_file_records_sent_at", table_name="file_records")
    op.drop_index("ix_file_records_conversation_id", table_name="file_records")
    op.drop_index("ix_file_records_parent_file_id", table_name="file_records")
    op.drop_column("file_records", "conversation_id")
    op.drop_column("file_records", "sent_at")
    op.drop_column("file_records", "sender")
    op.drop_column("file_records", "parent_file_id")
