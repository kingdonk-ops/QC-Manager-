"""materials: pass, fail and conditional outcomes with criterion, measured value and report on receipts and PMI

Revision ID: 7a4e9b2c5d13
Revises: 3c8d1f6a2b90
Create Date: 2026-11-23 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a4e9b2c5d13"
down_revision: str | Sequence[str] | None = "3c8d1f6a2b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("materials_receipts", "materials_pmi")


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.add_column(table, sa.Column('outcome', sa.String(length=12), nullable=True))
        op.add_column(table, sa.Column('criterion_id', sa.Integer(), nullable=True))
        op.add_column(table, sa.Column('measured_value', sa.String(length=40), nullable=True))
        op.add_column(table, sa.Column('conditional', sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column('report_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(TABLES):
        op.drop_column(table, 'report_id')
        op.drop_column(table, 'conditional')
        op.drop_column(table, 'measured_value')
        op.drop_column(table, 'criterion_id')
        op.drop_column(table, 'outcome')
