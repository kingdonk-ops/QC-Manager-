"""Reporting: KPI and portfolio dashboards, pivots and charts over any module's datasets, report templates,
and scheduled reports by email. Modules plug in through ``infrastructure.reporting`` (see docs/modules.md)."""

from ...infrastructure.reporting import ensure_loaded


async def on_startup() -> None:
    ensure_loaded()
