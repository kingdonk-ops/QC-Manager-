"""Materials for reporting: heats as a dataset and an uncertified-heats KPI."""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, Kpi, register_dataset, register_kpi
from .constants import HeatStatus, VerificationStatus
from .models import Heat, MillCertificate
from .service import read_heats


async def heat_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    heats = list((await db.execute(select(Heat).where(Heat.project_id == project_id).order_by(Heat.heat_number))).scalars())
    return [
        {**r, "received_on": date.fromisoformat(r["received_on"]) if r["received_on"] else None, "heats": 1}
        for r in await read_heats(db, heats)
    ]


register_dataset(
    Dataset(
        name="material_heats",
        module="materials",
        title="Heats and lots",
        permission="materials.read",
        columns=[
            Column("heat_number", "Heat"),
            Column("material_grade", "Grade"),
            Column("product_form", "Form"),
            Column("supplied_by", "Supplied by"),
            Column("received_on", "Received", "date"),
            Column("status", "Status"),
            Column("certificate_status", "Certificate"),
            Column("heats", "Count", "number"),
        ],
        rows=heat_rows,
    )
)


async def uncertified(db: AsyncSession, project_id: int) -> int:
    verified = select(MillCertificate.heat_id).where(MillCertificate.status == VerificationStatus.VERIFIED.value)
    return (
        await db.scalar(
            select(func.count()).where(
                Heat.project_id == project_id, Heat.status != HeatStatus.EXPECTED.value, Heat.id.not_in(verified)
            )
        )
        or 0
    )


register_kpi(
    Kpi(
        "materials.uncertified",
        "materials",
        "Heats without a verified certificate",
        uncertified,
        unit="count",
        good="down",
        thresholds=(0, 5),
        permission="materials.read",
    )
)
