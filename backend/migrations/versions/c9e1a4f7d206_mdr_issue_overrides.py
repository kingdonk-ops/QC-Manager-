"""mdr: dossier issue overrides

Revision ID: c9e1a4f7d206
Revises: f5d8b2a7c931
Create Date: 2026-11-24 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e1a4f7d206"
down_revision: str | Sequence[str] | None = "f5d8b2a7c931"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: a new table only; no existing row changes and no role is granted the new permission."""
    op.create_table(
        "mdr_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("purpose", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("gate_numbers", sa.JSON(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("report_code", sa.String(length=100), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["user.id"], name=op.f("fk_mdr_overrides_created_by_id_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["dossier_id"], ["mdr_dossiers.id"], name=op.f("fk_mdr_overrides_dossier_id_mdr_dossiers"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_mdr_overrides_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mdr_overrides")),
    )
    op.create_index("ix_mdr_overrides_dossier_reference", "mdr_overrides", ["dossier_id", "reference"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_mdr_overrides_dossier_reference", table_name="mdr_overrides")
    op.drop_table("mdr_overrides")
