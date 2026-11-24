"""issues: documentation category with a non-blocking default template

Revision ID: d3b7a9e15c48
Revises: c9e1a4f7d206
Create Date: 2026-11-24 14:00:00.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3b7a9e15c48"
down_revision: str | Sequence[str] | None = "c9e1a4f7d206"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "documentation"
TEMPLATE_KEY = "documentation-ncr"
SOURCE_TEMPLATE_KEY = "general-ncr"

categories = sa.table(
    "ncr_categories",
    sa.column("id", sa.Integer),
    sa.column("project_id", sa.Integer),
    sa.column("key", sa.String),
    sa.column("label", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("sort_order", sa.Integer),
    sa.column("allows_project_level", sa.Boolean),
    sa.column("pack_key", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
templates = sa.table(
    "ncr_templates",
    sa.column("id", sa.Integer),
    sa.column("project_id", sa.Integer),
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("issue_type", sa.String),
    sa.column("category", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("pack_key", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
revisions = sa.table(
    "ncr_template_revisions",
    sa.column("id", sa.Integer),
    sa.column("template_id", sa.Integer),
    sa.column("number", sa.Integer),
    sa.column("status", sa.String),
    sa.column("name", sa.String),
    sa.column("fields", sa.JSON),
    sa.column("default_origin", sa.String),
    sa.column("default_visibility", sa.String),
    sa.column("default_mdr_effect", sa.String),
    sa.column("completion_effect", sa.String),
    sa.column("default_severity", sa.String),
    sa.column("separate_close", sa.Boolean),
    sa.column("published_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
defaults = sa.table(
    "ncr_default_templates",
    sa.column("id", sa.Integer),
    sa.column("project_id", sa.Integer),
    sa.column("category", sa.String),
    sa.column("issue_type", sa.String),
    sa.column("template_id", sa.Integer),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
reports = sa.table("ncr_reports", sa.column("category", sa.String))


def upgrade() -> None:
    """Add the documentation category and its library template to a library that was seeded earlier.

    A database whose library has not been seeded yet gets the same rows from the seed on first use, so nothing is done
    for it here. Rerunning is harmless: every row is only added when it is missing."""
    bind = op.get_bind()
    now = datetime.now(UTC)
    if bind.scalar(sa.select(categories.c.id).where(categories.c.project_id.is_(None)).limit(1)) is None:
        return
    if bind.scalar(sa.select(categories.c.id).where(categories.c.project_id.is_(None), categories.c.key == CATEGORY)) is None:
        last = bind.scalar(sa.select(sa.func.max(categories.c.sort_order)).where(categories.c.project_id.is_(None)))
        bind.execute(
            sa.insert(categories).values(
                project_id=None,
                key=CATEGORY,
                label="Documentation",
                is_active=True,
                sort_order=(last or 0) + 1,
                allows_project_level=True,
                pack_key="system",
                created_at=now,
            )
        )
    template_id = bind.scalar(
        sa.select(templates.c.id).where(templates.c.project_id.is_(None), templates.c.key == TEMPLATE_KEY)
    )
    if template_id is None:
        # the fields are the general NCR's, so the report is worked through the same steps
        base = bind.scalar(
            sa.select(templates.c.id).where(templates.c.project_id.is_(None), templates.c.key == SOURCE_TEMPLATE_KEY)
        )
        fields = (
            bind.scalar(
                sa.select(revisions.c.fields)
                .where(revisions.c.template_id == base, revisions.c.status == "published")
                .order_by(revisions.c.number.desc())
                .limit(1)
            )
            if base is not None
            else None
        )
        template_id = bind.execute(
            sa.insert(templates)
            .values(
                project_id=None,
                key=TEMPLATE_KEY,
                name="Documentation NCR",
                issue_type="ncr",
                category=CATEGORY,
                is_active=True,
                pack_key="system",
                created_at=now,
            )
            .returning(templates.c.id)
        ).scalar_one()
        bind.execute(
            sa.insert(revisions).values(
                template_id=template_id,
                number=1,
                status="published",
                name="Documentation NCR",
                fields=fields or [],
                default_origin="qa",
                default_visibility="internal",
                default_mdr_effect="register_only",
                completion_effect="none",
                default_severity="minor",
                separate_close=False,
                published_at=now,
                created_at=now,
            )
        )
    mapped = bind.scalar(
        sa.select(defaults.c.id).where(
            defaults.c.project_id.is_(None), defaults.c.category == CATEGORY, defaults.c.issue_type == "ncr"
        )
    )
    if mapped is None:
        bind.execute(
            sa.insert(defaults).values(
                project_id=None, category=CATEGORY, issue_type="ncr", template_id=template_id, created_at=now
            )
        )


def downgrade() -> None:
    """Remove the library rows again, unless a report already uses the category: keys are never deleted once used."""
    bind = op.get_bind()
    if bind.scalar(sa.select(reports.c.category).where(reports.c.category == CATEGORY).limit(1)) is not None:
        return
    template_ids = sa.select(templates.c.id).where(templates.c.project_id.is_(None), templates.c.key == TEMPLATE_KEY)
    bind.execute(sa.delete(defaults).where(defaults.c.template_id.in_(template_ids)))
    bind.execute(sa.delete(revisions).where(revisions.c.template_id.in_(template_ids)))
    bind.execute(sa.delete(templates).where(templates.c.project_id.is_(None), templates.c.key == TEMPLATE_KEY))
    bind.execute(sa.delete(categories).where(categories.c.project_id.is_(None), categories.c.key == CATEGORY))
