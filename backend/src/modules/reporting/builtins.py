"""The templates every installation starts with. Seeded once (by ``builtin_key``); people copy and adapt them."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ReportTemplate

BUILTINS: list[dict[str, Any]] = [
    {
        "builtin_key": "monthly_progress",
        "name": "Monthly progress",
        "description": "Key figures, the cost summary by cost head, and the state of the task list.",
        "landscape": False,
        "sections": [
            {"type": "kpis", "title": "Key figures", "keys": []},
            {
                "type": "table",
                "title": "Cost summary",
                "dataset": "cvr_cost_heads",
                "columns": ["code", "description", "budget", "cost_to_date", "value_to_date", "forecast_cost", "variance"],
                "filters": {},
                "group_by": None,
                "sort_by": None,
                "descending": False,
                "limit": 500,
            },
            {
                "type": "chart",
                "title": "Tasks by status",
                "dataset": "tasks",
                "chart": "stacked",
                "x": "status",
                "y": ["tasks"],
                "agg": "sum",
                "group_by": "priority",
                "filters": {},
            },
            {
                "type": "table",
                "title": "Overdue tasks",
                "dataset": "tasks",
                "columns": ["code", "title", "assignee", "priority", "due_date"],
                "filters": {"overdue": True},
                "group_by": None,
                "sort_by": "due_date",
                "descending": False,
                "limit": 200,
            },
        ],
    },
    {
        "builtin_key": "cost_report",
        "name": "Cost report",
        "description": "Cost-value reconciliation: budget, cost, value, forecast and variance per cost head.",
        "landscape": True,
        "sections": [
            {
                "type": "kpis",
                "title": "Commercial position",
                "keys": [
                    "cvr.budget",
                    "cvr.cost_to_date",
                    "cvr.value_to_date",
                    "cvr.margin_pct",
                    "cvr.forecast_margin_pct",
                    "cvr.budget_variance_pct",
                ],
            },
            {
                "type": "chart",
                "title": "Budget against forecast by cost head",
                "dataset": "cvr_cost_heads",
                "chart": "bar",
                "x": "code",
                "y": ["budget", "forecast_cost"],
                "agg": "sum",
                "group_by": None,
                "filters": {},
            },
            {
                "type": "table",
                "title": "Cost heads",
                "dataset": "cvr_cost_heads",
                "columns": [],
                "filters": {},
                "group_by": None,
                "sort_by": None,
                "descending": False,
                "limit": 1000,
            },
            {
                "type": "table",
                "title": "Cashflow",
                "dataset": "cvr_cashflow",
                "columns": [],
                "filters": {},
                "group_by": None,
                "sort_by": "period",
                "descending": False,
                "limit": 240,
            },
        ],
    },
    {
        "builtin_key": "task_summary",
        "name": "Task summary",
        "description": "Task counts by status and priority, and the open tasks by assignee.",
        "landscape": False,
        "sections": [
            {"type": "kpis", "title": "Tasks", "keys": ["tasks.open", "tasks.overdue", "tasks.completion_rate"]},
            {
                "type": "pivot",
                "title": "Tasks by status and priority",
                "dataset": "tasks",
                "rows": ["status"],
                "columns": ["priority"],
                "values": [{"field": "*", "agg": "count"}],
                "filters": {},
            },
            {
                "type": "table",
                "title": "Open tasks",
                "dataset": "tasks",
                "columns": ["code", "title", "type", "status", "priority", "assignee", "due_date", "overdue"],
                "filters": {"done": False},
                "group_by": None,
                "sort_by": "due_date",
                "descending": False,
                "limit": 1000,
            },
        ],
    },
]


async def ensure_builtins(db: AsyncSession) -> None:
    have = set((await db.execute(select(ReportTemplate.builtin_key).where(ReportTemplate.builtin_key.is_not(None)))).scalars())
    missing = [b for b in BUILTINS if b["builtin_key"] not in have]
    if not missing:
        return
    for b in missing:
        db.add(ReportTemplate(**b))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # another request seeded them first
