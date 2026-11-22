"""Reporting and export providers: modules expose datasets, KPIs and importers here.

    # src/modules/punch_list/reporting.py
    from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi

    register_dataset(Dataset("punch_items", "punch_list", "Punch items", [Column("code", "Code"), ...],
                             rows=punch_rows, permission="punch_list.read"))
    register_kpi(Kpi("punch_list.open", "punch_list", "Open snags", open_snags, unit="count", good="down"))

See "Reporting and export providers" in docs/modules.md.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .registry import (
    Column,
    Dataset,
    Importer,
    ImportField,
    ImportJob,
    ImportReport,
    Kpi,
    all_datasets,
    all_importers,
    all_kpis,
    available_datasets,
    available_importers,
    available_kpis,
    ensure_loaded,
    find_dataset,
    find_importer,
    register_dataset,
    register_importer,
    register_kpi,
    unregister,
)
from .tables import apply_filters


async def load_rows(
    db: AsyncSession,
    dataset: Dataset,
    project_id: int | None,
    filters: dict[str, Any] | None,
    visible_projects: set[int] | None,
) -> list[dict[str, Any]]:
    """The dataset's rows, narrowed to the projects the caller may read (``None``: no limit) and filtered."""
    rows = await dataset.rows(db, project_id, dict(filters or {}))
    if visible_projects is not None:
        rows = [r for r in rows if r.get("project_id") is None or r["project_id"] in visible_projects]
    return apply_filters(dataset, rows, filters)


__all__ = [
    "Column",
    "Dataset",
    "ImportField",
    "ImportJob",
    "ImportReport",
    "Importer",
    "Kpi",
    "all_datasets",
    "all_importers",
    "all_kpis",
    "available_datasets",
    "available_importers",
    "available_kpis",
    "ensure_loaded",
    "find_dataset",
    "find_importer",
    "load_rows",
    "register_dataset",
    "register_importer",
    "register_kpi",
    "unregister",
]
