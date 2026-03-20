"""add_md5_hash_to_file_records

Revision ID: f1a1e1b1c1d1
Revises: e6b4f3c2a1d0, 598a0c6a49e2
Create Date: 2026-03-20 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a1e1b1c1d1"
down_revision: Union[str, Sequence[str], None] = ("e6b4f3c2a1d0", "598a0c6a49e2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("file_records", sa.Column("md5_hash", sa.String(), nullable=True))
    op.create_index(op.f("ix_file_records_md5_hash"), "file_records", ["md5_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_file_records_md5_hash"), table_name="file_records")
    op.drop_column("file_records", "md5_hash")
