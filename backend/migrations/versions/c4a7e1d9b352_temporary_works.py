"""safety: temporary works register

Revision ID: c4a7e1d9b352
Revises: b2e6a8c4f017
Create Date: 2026-11-23 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a7e1d9b352"
down_revision: str | Sequence[str] | None = "b2e6a8c4f017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "temporary_works_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("family", sa.String(length=24), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("design_check_category", sa.Integer(), nullable=True),
        sa.Column("designer", sa.String(length=200), nullable=True),
        sa.Column("checker", sa.String(length=200), nullable=True),
        sa.Column("coordinator_name", sa.String(length=200), nullable=True),
        sa.Column("coordinator_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("held_from", sa.String(length=24), nullable=True),
        sa.Column("required_load_on", sa.Date(), nullable=True),
        sa.Column("required_strike_on", sa.Date(), nullable=True),
        sa.Column("design_due_on", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("asset_node_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("scaffold_id", sa.Integer(), nullable=True),
        sa.Column("related_refs", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("breach_notified_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_temporary_works_items_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["coordinator_user_id"],
            ["user.id"],
            name=op.f("fk_temporary_works_items_coordinator_user_id_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["asset_node_id"],
            ["asset_nodes.id"],
            name=op.f("fk_temporary_works_items_asset_node_id_asset_nodes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temporary_works_items")),
        sa.UniqueConstraint("project_id", "reference", name="uq_temporary_works_items_reference"),
    )
    op.create_index("ix_temporary_works_items_project_status", "temporary_works_items", ["project_id", "status"], unique=False)
    op.create_index("ix_temporary_works_items_scaffold", "temporary_works_items", ["scaffold_id"], unique=False)

    op.create_table(
        "temporary_works_permits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("issued_by_name", sa.String(length=200), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("closed_by_id", sa.Integer(), nullable=True),
        sa.Column("inspection_id", sa.Integer(), nullable=True),
        sa.Column("design_check_accepted", sa.Boolean(), nullable=False),
        sa.Column("inspection_passed", sa.Boolean(), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("expiry_notified_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_temporary_works_permits_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["temporary_works_items.id"],
            name=op.f("fk_temporary_works_permits_item_id_temporary_works_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temporary_works_permits")),
        sa.UniqueConstraint("project_id", "number", name="uq_temporary_works_permits_number"),
    )
    op.create_index(op.f("ix_temporary_works_permits_item_id"), "temporary_works_permits", ["item_id"], unique=False)
    op.create_index(
        "ix_temporary_works_permits_project_status", "temporary_works_permits", ["project_id", "status"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_temporary_works_permits_project_status", table_name="temporary_works_permits")
    op.drop_index(op.f("ix_temporary_works_permits_item_id"), table_name="temporary_works_permits")
    op.drop_table("temporary_works_permits")
    op.drop_index("ix_temporary_works_items_scaffold", table_name="temporary_works_items")
    op.drop_index("ix_temporary_works_items_project_status", table_name="temporary_works_items")
    op.drop_table("temporary_works_items")
