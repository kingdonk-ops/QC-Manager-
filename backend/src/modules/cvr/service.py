from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ..projects.models import Project
from .exceptions import CostHeadCodeTakenError, CostHeadNotFoundError
from .models import CashflowPeriod, CostHead
from .schemas import CashflowPeriodIn, CashflowPeriodRead, CostHeadRead, CvrSummary


def _pct(part: Decimal, whole: Decimal) -> float | None:
    return round(float(part / whole * 100), 2) if whole else None


class CvrService:
    async def cost_heads(self, db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(CostHead).where(CostHead.project_id == project_id).order_by(CostHead.sort_order, CostHead.code)
            )
        ).scalars()

        return [CostHeadRead.model_validate(row).model_dump(mode="json") for row in rows]

    async def _head(self, db: AsyncSession, project_id: int, head_id: int) -> CostHead:
        head = await db.get(CostHead, head_id)
        if head is None or head.project_id != project_id:
            raise CostHeadNotFoundError(f"Cost head {head_id} not found")

        return head

    async def _commit(self, db: AsyncSession) -> None:
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise CostHeadCodeTakenError("Code taken") from exc

    async def add_cost_head(self, db: AsyncSession, project_id: int, values: dict[str, Any]) -> dict[str, Any]:
        head = CostHead(project_id=project_id, **values)
        db.add(head)
        await self._commit(db)
        await publish("cvr.cost_head.created", {"project_id": project_id, "cost_head_id": head.id})

        return CostHeadRead.model_validate(head).model_dump(mode="json")

    async def update_cost_head(self, db: AsyncSession, project_id: int, head_id: int, values: dict[str, Any]) -> dict[str, Any]:
        head = await self._head(db, project_id, head_id)
        for key, value in values.items():
            if value is not None:
                setattr(head, key, value)
        await self._commit(db)
        await publish("cvr.cost_head.updated", {"project_id": project_id, "cost_head_id": head.id, "fields": sorted(values)})

        return CostHeadRead.model_validate(head).model_dump(mode="json")

    async def delete_cost_head(self, db: AsyncSession, project_id: int, head_id: int) -> None:
        await db.delete(await self._head(db, project_id, head_id))
        await db.commit()

    async def summary(self, db: AsyncSession, project: Project) -> CvrSummary:
        totals = (
            await db.execute(
                select(
                    func.coalesce(func.sum(CostHead.budget), 0),
                    func.coalesce(func.sum(CostHead.cost_to_date), 0),
                    func.coalesce(func.sum(CostHead.value_to_date), 0),
                    func.coalesce(func.sum(CostHead.forecast_cost), 0),
                    func.coalesce(func.sum(CostHead.forecast_value), 0),
                ).where(CostHead.project_id == project.id)
            )
        ).one()
        budget, cost, value, f_cost, f_value = (Decimal(x) for x in totals)

        return CvrSummary(
            project_id=project.id,
            currency=project.currency,
            budget=budget,
            cost_to_date=cost,
            value_to_date=value,
            margin_to_date=value - cost,
            margin_to_date_pct=_pct(value - cost, value),
            forecast_cost=f_cost,
            forecast_value=f_value,
            forecast_margin=f_value - f_cost,
            forecast_margin_pct=_pct(f_value - f_cost, f_value),
        )

    async def cashflow(self, db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(CashflowPeriod).where(CashflowPeriod.project_id == project_id).order_by(CashflowPeriod.period)
            )
        ).scalars()

        return [CashflowPeriodRead.model_validate(row).model_dump(mode="json") for row in rows]

    async def set_cashflow(self, db: AsyncSession, project_id: int, periods: list[CashflowPeriodIn]) -> list[dict[str, Any]]:
        """Replace the project's cashflow with ``periods``; a month sent twice keeps the last."""
        by_month = {p.period: p for p in periods}
        await db.execute(delete(CashflowPeriod).where(CashflowPeriod.project_id == project_id))
        db.add_all([CashflowPeriod(project_id=project_id, **p.model_dump()) for p in by_month.values()])
        await db.commit()

        return await self.cashflow(db, project_id)
