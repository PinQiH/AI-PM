"""add_cancel_requested_to_file_records

Revision ID: e6b4f3c2a1d0
Revises: d4f2a7c8b9e1
Create Date: 2026-03-16 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6b4f3c2a1d0"
down_revision: Union[str, None] = "d4f2a7c8b9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "file_records",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("file_records", "cancel_requested", server_default=None)


def downgrade() -> None:
    op.drop_column("file_records", "cancel_requested")
