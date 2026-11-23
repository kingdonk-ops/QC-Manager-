"""safety: temporary works soft delete

Revision ID: d8c3f1a6e925
Revises: c4a7e1d9b352
Create Date: 2026-11-23 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8c3f1a6e925"
down_revision: str | Sequence[str] | None = "c4a7e1d9b352"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("temporary_works_items", "temporary_works_permits")


def upgrade() -> None:
    """Upgrade schema: a tombstone marker on items and permits (nothing is ever physically deleted)."""
    for table in TABLES:
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deleted_by_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(TABLES):
        op.drop_column(table, "deleted_by_id")
        op.drop_column(table, "deleted_at")
