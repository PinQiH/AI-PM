"""Change embedding dimension to 768 for Local LLM

Revision ID: 8c9d0a1b2c3d
Revises: f1a1e1b1c1d1
Create Date: 2026-04-01 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '8c9d0a1b2c3d'
down_revision: Union[str, None] = 'f1a1e1b1c1d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 由於 pgvector Vector 類型維度固定，強制更換
    # 注意：這裡會刪除舊欄位，請確保資料已清空或是可重建
    op.drop_column('knowledge_base', 'embedding')
    op.add_column('knowledge_base', sa.Column('embedding', Vector(768), nullable=True))

def downgrade() -> None:
    op.drop_column('knowledge_base', 'embedding')
    op.add_column('knowledge_base', sa.Column('embedding', Vector(1536), nullable=True))
