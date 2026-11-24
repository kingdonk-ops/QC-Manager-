"""quality: standalone hold, witness, surveillance and review gates

Revision ID: 9f1b3d7e6c24
Revises: 7a4e9b2c5d13
Create Date: 2026-11-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f1b3d7e6c24"
down_revision: str | Sequence[str] | None = "7a4e9b2c5d13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "inspections_gates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=14), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=True),
        sa.Column("criterion_id", sa.Integer(), nullable=True),
        sa.Column("attachment_kind", sa.String(length=12), nullable=True),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("package_ref", sa.String(length=100), nullable=True),
        sa.Column("blocks_progress", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("released_by_id", sa.Integer(), nullable=True),
        sa.Column("released_level", sa.String(length=32), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_justification", sa.Text(), nullable=True),
        sa.Column("release_ip", sa.String(length=64), nullable=True),
        sa.Column("release_digest", sa.String(length=64), nullable=True),
        sa.Column("waived_by_id", sa.Integer(), nullable=True),
        sa.Column("waiver_reason", sa.Text(), nullable=True),
        sa.Column("approval_ref", sa.String(length=100), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("supplementary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_inspections_gates_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_inspections_gates_inspection_id_inspections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["criterion_id"],
            ["inspections_criteria.id"],
            name=op.f("fk_inspections_gates_criterion_id_inspections_criteria"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspections_gates")),
        sa.UniqueConstraint("project_id", "number", name="uq_inspections_gates_number"),
    )
    op.create_index(op.f("ix_inspections_gates_inspection_id"), "inspections_gates", ["inspection_id"], unique=False)
    op.create_index(op.f("ix_inspections_gates_criterion_id"), "inspections_gates", ["criterion_id"], unique=False)
    op.create_index(
        "ix_inspections_gates_attachment",
        "inspections_gates",
        ["project_id", "attachment_kind", "attachment_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_inspections_gates_attachment", table_name="inspections_gates")
    op.drop_index(op.f("ix_inspections_gates_criterion_id"), table_name="inspections_gates")
    op.drop_index(op.f("ix_inspections_gates_inspection_id"), table_name="inspections_gates")
    op.drop_table("inspections_gates")
