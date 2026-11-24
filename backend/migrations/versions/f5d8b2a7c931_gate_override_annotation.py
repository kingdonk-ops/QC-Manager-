"""quality: dossier issue override annotation on quality gates

Revision ID: f5d8b2a7c931
Revises: a3f9c6d1b284
Create Date: 2026-11-23 22:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5d8b2a7c931"
down_revision: str | Sequence[str] | None = "a3f9c6d1b284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: both columns are empty for every existing gate, which reads as not overridden."""
    op.add_column("inspections_gates", sa.Column("override_id", sa.Integer(), nullable=True))
    op.add_column("inspections_gates", sa.Column("override_ref", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("inspections_gates", "override_ref")
    op.drop_column("inspections_gates", "override_id")
