"""add_created_updated_to_agent_executions

Revision ID: 0fda01743d48
Revises: 2fa45216c3cb
Create Date: 2026-11-10 21:58:29.892471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '0fda01743d48'
down_revision: Union[str, None] = '2fa45216c3cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for ALTER TABLE operations
    with op.batch_alter_table('agent_executions') as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    # SQLite requires batch mode for ALTER TABLE operations
    with op.batch_alter_table('agent_executions') as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')