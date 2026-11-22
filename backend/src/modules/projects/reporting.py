"""Projects as a dataset, for the export hub and cross-project reports."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, register_dataset
from .constants import REGIONS
from .models import Project


async def project_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    query = select(Project).order_by(Project.code)
    if project_id is not None:
        query = query.where(Project.id == project_id)
    return [
        {
            "project_id": p.id,
            "code": p.code,
            "name": p.name,
            "client_name": p.client_name,
            "location": p.location,
            "region": p.region,
            "region_name": REGIONS.get(p.region or "", {}).get("name"),
            "status": p.status,
            "currency": p.currency,
            "start_date": p.start_date,
            "end_date": p.end_date,
        }
        for p in (await db.execute(query)).scalars()
    ]


register_dataset(
    Dataset(
        name="projects",
        module="projects",
        title="Projects",
        description="Every project you can see, with its client, region and dates.",
        project_scoped=False,
        columns=[
            Column("project_id", "Id", "number", aggregatable=False),
            Column("code", "Code"),
            Column("name", "Name"),
            Column("client_name", "Client"),
            Column("location", "Location"),
            Column("region", "Region"),
            Column("region_name", "Region name"),
            Column("status", "Status"),
            Column("currency", "Currency"),
            Column("start_date", "Start", "date"),
            Column("end_date", "End", "date"),
        ],
        rows=project_rows,
    )
)
