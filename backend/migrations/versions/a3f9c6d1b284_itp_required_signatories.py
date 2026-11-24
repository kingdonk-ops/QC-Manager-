"""quality: required signatory count on inspection records and the additional-signatory uniqueness backstop

Revision ID: a3f9c6d1b284
Revises: e7b4d2a9c150
Create Date: 2026-11-23 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c6d1b284"
down_revision: str | Sequence[str] | None = "e7b4d2a9c150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: every existing record reads one required signatory through the server default."""
    op.add_column(
        "inspections",
        sa.Column("required_signatories", sa.Integer(), server_default="1", nullable=False),
    )
    # The role has no rows yet, so the index cannot fail on old data; it limits itself to live statuses so a voided
    # signature never blocks signing again after the record changed.
    op.create_index(
        "uq_inspections_signatures_additional_live",
        "inspections_signatures",
        ["inspection_id", "signer_user_id", "role"],
        unique=True,
        postgresql_where=sa.text("role = 'additional_signatory' AND status IN ('valid', 'provisional')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_inspections_signatures_additional_live",
        table_name="inspections_signatures",
        postgresql_where=sa.text("role = 'additional_signatory' AND status IN ('valid', 'provisional')"),
    )
    op.drop_column("inspections", "required_signatories")
