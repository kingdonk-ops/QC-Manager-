from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..user.models import User
from .constants import BANDS, FLOW, OPEN_STATUSES, Band, Impact, RiskStatus, band_of
from .models import Risk
from .schemas import RiskBand, RiskCategoryTotal, RiskMatrix, RiskMatrixCell, RiskRead

CENT = Decimal("0.01")
ENTITY = "risk"


class RiskNotFoundError(ResourceNotFoundError):
    public_detail = "Risk not found."


class UnknownOwnerError(ValidationError):
    public_detail = "The owner must be an existing user."


def link_of(risk: Risk) -> str:
    return f"/risks?project={risk.project_id}&risk={risk.id}"


def exposure(probability: Decimal | None, cost: Decimal) -> Decimal:
    return (Decimal(probability or 0) * Decimal(cost)).quantize(CENT)


def _band_filter(band: Band) -> Any:
    _, _, low, high = next(b for b in BANDS if b[0] == band)
    return Risk.probability.between(low, high)


async def user_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


async def read_risks(db: AsyncSession, risks: list[Risk], mode: str = "json") -> list[dict[str, Any]]:
    names = await user_names(db, {r.owner_id for r in risks if r.owner_id})
    today = date.today()
    out = []
    for r in risks:
        read = RiskRead.model_validate(r).model_copy(
            update={
                "owner_name": names.get(r.owner_id) if r.owner_id else None,
                "band": band_of(Decimal(r.probability)).value,
                "exposure": exposure(r.probability, r.cost_impact),
                "residual_exposure": exposure(r.residual_probability, r.cost_impact)
                if r.residual_probability is not None
                else None,
                "review_due": bool(r.review_date and r.review_date <= today and r.status != RiskStatus.CLOSED),
            }
        )
        out.append(read.model_dump(mode=mode))
    return out


def filters(
    project_id: int,
    *,
    status: str | None = None,
    category: str | None = None,
    impact: str | None = None,
    band: Band | None = None,
    owner_id: int | None = None,
    open_only: bool = False,
    search: str | None = None,
) -> list[Any]:
    where: list[Any] = [Risk.project_id == project_id]
    if status:
        where.append(Risk.status == status)
    if category:
        where.append(Risk.category == category)
    if impact:
        where.append(Risk.impact == impact)
    if band:
        where.append(_band_filter(band))
    if owner_id:
        where.append(Risk.owner_id == owner_id)
    if open_only:
        where.append(Risk.status.in_([s.value for s in OPEN_STATUSES]))
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Risk.title + " " + Risk.code).like(like),
                func.lower(func.coalesce(Risk.description, "")).like(like),
            )
        )
    return where


EXPOSURE = Risk.probability * Risk.cost_impact


async def page(db: AsyncSession, where: list[Any], skip: int, limit: int, sort: str) -> dict[str, Any]:
    total = await db.scalar(select(func.count()).select_from(Risk).where(*where))
    order = [EXPOSURE.desc(), Risk.id] if sort == "exposure" else [Risk.id]
    rows = (await db.execute(select(Risk).where(*where).order_by(*order).offset(skip).limit(limit))).scalars()
    return {"data": await read_risks(db, list(rows)), "total_count": total or 0}


async def get_risk(db: AsyncSession, risk_id: int) -> Risk:
    risk = await db.get(Risk, risk_id)
    if risk is None:
        raise RiskNotFoundError(f"Risk {risk_id} not found")
    return risk


async def _check_owner(db: AsyncSession, owner_id: int | None) -> None:
    if owner_id is not None and await db.get(User, owner_id) is None:
        raise UnknownOwnerError(str(owner_id))


async def _tell_owner(db: AsyncSession, risk: Risk, actor_id: int) -> None:
    if risk.owner_id:
        await notify(
            db,
            [risk.owner_id],
            Category.ASSIGNMENT,
            f"{risk.code}: {risk.title}",
            body="You are the owner of this risk.",
            link=link_of(risk),
            entity=(ENTITY, risk.id),
            actor_id=actor_id,
        )


def _plain(values: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.value if hasattr(v, "value") else v) for k, v in values.items()}


async def create(db: AsyncSession, values: dict[str, Any], actor_id: int) -> Risk:
    await _check_owner(db, values.get("owner_id"))
    project_id = values.pop("project_id")
    risk = Risk(
        project_id=project_id,
        code=await next_reference(db, "R", project_id),
        created_by_id=actor_id,
        **_plain(values),
    )
    db.add(risk)
    await db.flush()
    await record_transition(db, ENTITY, risk.id, None, risk.status, actor_id)
    await _tell_owner(db, risk, actor_id)
    await db.commit()
    await publish("risk.risk.created", {"project_id": project_id, "risk_id": risk.id})
    return risk


async def update(db: AsyncSession, risk: Risk, values: dict[str, Any], actor_id: int) -> Risk:
    before_owner = risk.owner_id
    if "owner_id" in values:
        await _check_owner(db, values["owner_id"])
    nullable = {
        "description",
        "cause",
        "effect",
        "owner_id",
        "mitigation",
        "contingency",
        "residual_probability",
        "residual_impact",
        "response",
        "review_date",
    }
    for key, value in _plain(values).items():
        if value is None and key not in nullable:
            continue
        setattr(risk, key, value)
    if risk.owner_id and risk.owner_id != before_owner:
        await _tell_owner(db, risk, actor_id)
    await db.commit()
    await publish("risk.risk.updated", {"project_id": risk.project_id, "risk_id": risk.id, "fields": sorted(values)})
    return risk


async def transition(db: AsyncSession, risk: Risk, target: str, actor_id: int, note: str | None) -> Risk:
    assert_transition(FLOW, risk.status, target)
    before = risk.status
    risk.status = target
    await record_transition(db, ENTITY, risk.id, before, target, actor_id, note)
    watchers = {risk.owner_id, risk.created_by_id} - {None}
    await notify(
        db,
        [w for w in watchers if w],
        Category.STATUS,
        f"{risk.code} is now {target}",
        body=risk.title,
        link=link_of(risk),
        entity=(ENTITY, risk.id),
        actor_id=actor_id,
    )
    await db.commit()
    await publish(f"risk.risk.{target}", {"project_id": risk.project_id, "risk_id": risk.id, "from": before})
    return risk


async def matrix(db: AsyncSession, project: Project, include_closed: bool = False) -> RiskMatrix:
    where = filters(project.id, open_only=not include_closed)
    risks = list((await db.execute(select(Risk).where(*where))).scalars())
    count = await db.scalar(select(func.count()).select_from(Risk).where(Risk.project_id == project.id)) or 0

    cells: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    categories: dict[str, list[Decimal]] = defaultdict(list)
    for r in risks:
        e = exposure(r.probability, r.cost_impact)
        cells[(band_of(Decimal(r.probability)).value, r.impact)].append(e)
        categories[r.category].append(e)

    ranked = sorted(risks, key=lambda r: (-exposure(r.probability, r.cost_impact), r.id))[:10]
    return RiskMatrix(
        project_id=project.id,
        currency=project.currency,
        bands=[RiskBand(key=k.value, label=label, min=lo, max=hi) for k, label, lo, hi in BANDS],
        impacts=[i.value for i in Impact],
        cells=[
            RiskMatrixCell(band=b.value, impact=i.value, count=len(cells[(b, i)]), exposure=sum(cells[(b, i)], Decimal(0)))
            for b, *_ in BANDS
            for i in Impact
        ],
        total_exposure=sum((exposure(r.probability, r.cost_impact) for r in risks), Decimal(0)),
        total_residual_exposure=sum(
            (
                exposure(r.residual_probability if r.residual_probability is not None else r.probability, r.cost_impact)
                for r in risks
            ),
            Decimal(0),
        ),
        total_schedule_days=sum(r.schedule_impact_days for r in risks),
        count=count,
        open_count=sum(1 for r in risks if r.status in {s.value for s in OPEN_STATUSES}),
        high_critical_count=sum(1 for r in risks if r.impact in (Impact.HIGH, Impact.CRITICAL)),
        by_category=sorted(
            (RiskCategoryTotal(category=c, count=len(v), exposure=sum(v, Decimal(0))) for c, v in categories.items()),
            key=lambda c: -c.exposure,
        ),
        top=[RiskRead(**r) for r in await read_risks(db, ranked)],
    )


EXPORT_COLUMNS = [
    ("code", "Code"),
    ("title", "Title"),
    ("category", "Category"),
    ("status", "Status"),
    ("probability", "Probability"),
    ("impact", "Impact"),
    ("cost_impact", "Cost impact"),
    ("exposure", "Exposure"),
    ("schedule_impact_days", "Schedule impact (days)"),
    ("owner_name", "Owner"),
    ("response", "Response"),
    ("mitigation", "Mitigation"),
    ("contingency", "Contingency"),
    ("residual_probability", "Residual probability"),
    ("residual_impact", "Residual impact"),
    ("residual_exposure", "Residual exposure"),
    ("review_date", "Review date"),
    ("cause", "Cause"),
    ("effect", "Effect"),
    ("description", "Description"),
]
