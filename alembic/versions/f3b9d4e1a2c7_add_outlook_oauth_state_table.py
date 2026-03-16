"""add_outlook_oauth_state_table

Revision ID: f3b9d4e1a2c7
Revises: c2a6f4d8e9b1
Create Date: 2026-03-13 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b9d4e1a2c7"
down_revision: Union[str, None] = "c2a6f4d8e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outlook_oauth_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_token", sa.String(), nullable=False),
        sa.Column("default_project_name", sa.String(), nullable=False),
        sa.Column("source_folder_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_token"),
    )
    op.create_index("ix_outlook_oauth_states_id", "outlook_oauth_states", ["id"], unique=False)
    op.create_index("ix_outlook_oauth_states_state_token", "outlook_oauth_states", ["state_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_outlook_oauth_states_state_token", table_name="outlook_oauth_states")
    op.drop_index("ix_outlook_oauth_states_id", table_name="outlook_oauth_states")
    op.drop_table("outlook_oauth_states")
