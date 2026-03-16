"""drop_unique_on_outlook_mailbox_project

Revision ID: a1e6c9d4b2f0
Revises: f3b9d4e1a2c7
Create Date: 2026-03-13 18:16:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1e6c9d4b2f0"
down_revision: Union[str, None] = "f3b9d4e1a2c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("outlook_mailboxes_project_id_key", "outlook_mailboxes", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("outlook_mailboxes_project_id_key", "outlook_mailboxes", ["project_id"])
