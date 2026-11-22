"""Issues for reporting: the issue register as a dataset (staff only: it includes internal issues) and QMS KPIs
(open Cat A punches, open NCRs, loosening flag overrides)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .constants import TERMINAL, IssueType, PunchCategory
from .models import IssueFlagOverride, Ncr
from .service import read_ncrs

STAFF = "ncr.read,projects.read"


async def issue_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(Ncr).where(Ncr.project_id == project_id).order_by(Ncr.code))).scalars())
    return [
        {
            "project_id": r["project_id"],
            "code": r["code"],
            "title": r["title"],
            "issue_type": r["issue_type"],
            "category": r["category"],
            "template": r["template_name"],
            "status": r["status"],
            "open": r["is_open"],
            "punch_category": r["punch_category"],
            "severity": r["severity"],
            "origin": r["origin"],
            "visibility": r["visibility"],
            "mdr_effect": r["mdr_effect"],
            "anchor": r["anchor_label"],
            "responsible": r["responsible_user_name"] or r["responsible_contact_name"] or r["responsible_company_name"],
            "raised": r["raised_on"],
            "due": r["due_date"],
            "closed": (r["closed_at"] or "")[:10] or None,
            "total_cost": float(r["total_cost"]),
            "issues": 1,
        }
        for r in await read_ncrs(db, rows)
    ]


register_dataset(
    Dataset(
        name="issues",
        module="ncr",
        title="Issues (punch and NCR)",
        description="Every punch item and NCR with type, Cat A/B/C, status, flags and anchor.",
        permission=STAFF,
        columns=[
            Column("code", "No."),
            Column("title", "Title"),
            Column("issue_type", "Type"),
            Column("category", "Category"),
            Column("template", "Template"),
            Column("status", "Status"),
            Column("open", "Open", "bool"),
            Column("punch_category", "Cat"),
            Column("severity", "Severity"),
            Column("origin", "Origin"),
            Column("visibility", "Visibility"),
            Column("mdr_effect", "MDR effect"),
            Column("anchor", "Anchor"),
            Column("responsible", "Responsible"),
            Column("raised", "Raised", "date"),
            Column("due", "Due", "date"),
            Column("closed", "Closed", "date"),
            Column("total_cost", "Cost of quality", "money"),
            Column("issues", "Count", "number"),
        ],
        rows=issue_rows,
    )
)


async def _count(db: AsyncSession, project_id: int, *where: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(Ncr).where(Ncr.project_id == project_id, *where)) or 0)


async def open_cat_a(db: AsyncSession, project_id: int) -> int:
    return await _count(
        db, project_id, Ncr.issue_type == IssueType.PUNCH, Ncr.punch_category == PunchCategory.A, Ncr.status.not_in(TERMINAL)
    )


async def open_ncrs(db: AsyncSession, project_id: int) -> int:
    return await _count(db, project_id, Ncr.issue_type == IssueType.NCR, Ncr.status.not_in(TERMINAL))


async def loosening_overrides(db: AsyncSession, project_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(IssueFlagOverride.project_id == project_id, IssueFlagOverride.loosening.is_(True))
        )
        or 0
    )


register_kpi(
    Kpi(
        "ncr.open_cat_a",
        "ncr",
        "Open Cat A punch",
        open_cat_a,
        unit="count",
        good="down",
        thresholds=(0, 5),
        permission=STAFF,
        description="Open Cat A punch items block work completion.",
        portfolio=True,
    )
)
register_kpi(Kpi("ncr.open_ncrs", "ncr", "Open NCRs", open_ncrs, unit="count", good="down", permission=STAFF, portfolio=True))
register_kpi(
    Kpi(
        "ncr.loosening_overrides",
        "ncr",
        "Loosening flag overrides",
        loosening_overrides,
        unit="count",
        good="down",
        thresholds=(0, 3),
        permission=STAFF,
        description="Issue flags loosened by override (MDR effect towards excluded, completion effect, visibility).",
    )
)
