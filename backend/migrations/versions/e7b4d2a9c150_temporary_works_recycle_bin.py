"""safety: temporary works recycle bin and Deleted folder

Revision ID: e7b4d2a9c150
Revises: d8c3f1a6e925
Create Date: 2026-11-23 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b4d2a9c150"
down_revision: str | Sequence[str] | None = "d8c3f1a6e925"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("temporary_works_items", "temporary_works_permits")


def upgrade() -> None:
    """Upgrade schema: where a deleted record sits (bin or folder), and each project's bin retention."""
    for table in TABLES:
        op.add_column(table, sa.Column("deleted_kind", sa.String(length=8), nullable=True))
        op.create_index(f"ix_{table}_deleted", table, ["deleted_kind", "deleted_at"], unique=False)
        # Everything deleted before the bin existed was kept as a tombstone: it belongs in the Deleted folder.
        op.execute(sa.text(f"UPDATE {table} SET deleted_kind = 'folder' WHERE deleted_at IS NOT NULL"))
    op.create_table(
        "temporary_works_settings",
        sa.Column("project_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("bin_retention_days", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_temporary_works_settings_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_temporary_works_settings")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("temporary_works_settings")
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_deleted", table_name=table)
        op.drop_column(table, "deleted_kind")
