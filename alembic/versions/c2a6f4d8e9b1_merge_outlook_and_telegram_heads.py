"""merge_outlook_and_telegram_heads

Revision ID: c2a6f4d8e9b1
Revises: 7b7f3d1e4c2a, b7d14c2f9e31
Create Date: 2026-03-13 16:55:00.000000

"""
from typing import Sequence, Union


revision: str = "c2a6f4d8e9b1"
down_revision: Union[str, Sequence[str], None] = ("7b7f3d1e4c2a", "b7d14c2f9e31")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
