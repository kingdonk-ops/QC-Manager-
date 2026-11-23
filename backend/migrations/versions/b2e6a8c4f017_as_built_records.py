"""quality: as-built records

Revision ID: b2e6a8c4f017
Revises: 9f1b3d7e6c24
Create Date: 2026-11-23 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e6a8c4f017"
down_revision: str | Sequence[str] | None = "9f1b3d7e6c24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "as_built_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("discipline", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("capture_method", sa.String(length=24), nullable=False),
        sa.Column("instrument", sa.String(length=200), nullable=True),
        sa.Column("calibration_ref", sa.String(length=100), nullable=True),
        sa.Column("accuracy_class", sa.String(length=12), nullable=False),
        sa.Column("accuracy_value", sa.String(length=40), nullable=True),
        sa.Column("accuracy_unit", sa.String(length=30), nullable=True),
        sa.Column("coordinate_system", sa.String(length=100), nullable=True),
        sa.Column("surveyed_on", sa.Date(), nullable=True),
        sa.Column("surveyed_by_id", sa.Integer(), nullable=True),
        sa.Column("criterion_id", sa.Integer(), nullable=True),
        sa.Column("measured_value", sa.String(length=40), nullable=True),
        sa.Column("deviation_value", sa.String(length=40), nullable=True),
        sa.Column("tolerance_result", sa.String(length=16), nullable=False),
        sa.Column("source_kind", sa.String(length=24), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("deviation_map_ref", sa.String(length=300), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verifier_notes", sa.Text(), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("legal_record", sa.Boolean(), nullable=False),
        sa.Column("signed_by_id", sa.Integer(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_ip", sa.String(length=64), nullable=True),
        sa.Column("signed_digest", sa.String(length=64), nullable=True),
        sa.Column("signature_notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("supplementary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_as_built_records_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["criterion_id"],
            ["inspections_criteria.id"],
            name=op.f("fk_as_built_records_criterion_id_inspections_criteria"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["asset_nodes.id"], name=op.f("fk_as_built_records_node_id_asset_nodes"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["asset_items.id"], name=op.f("fk_as_built_records_item_id_asset_items"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_as_built_records")),
        sa.UniqueConstraint("project_id", "number", name="uq_as_built_records_number"),
    )
    op.create_index(op.f("ix_as_built_records_project_id"), "as_built_records", ["project_id"], unique=False)
    op.create_index(op.f("ix_as_built_records_criterion_id"), "as_built_records", ["criterion_id"], unique=False)
    op.create_index(op.f("ix_as_built_records_node_id"), "as_built_records", ["node_id"], unique=False)
    op.create_index(op.f("ix_as_built_records_item_id"), "as_built_records", ["item_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_as_built_records_item_id"), table_name="as_built_records")
    op.drop_index(op.f("ix_as_built_records_node_id"), table_name="as_built_records")
    op.drop_index(op.f("ix_as_built_records_criterion_id"), table_name="as_built_records")
    op.drop_index(op.f("ix_as_built_records_project_id"), table_name="as_built_records")
    op.drop_table("as_built_records")
