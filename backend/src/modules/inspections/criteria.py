"""The acceptance-criteria library: lookup with project scoping, create and update with the freeze rule, and the
delete guard. Holders are found by scanning the mapped tables for a ``criterion_id`` column, so materials, gates and
as-built tables are counted without importing those modules."""

from typing import Any

from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database.session import Base
from ...infrastructure.http_exceptions import ConflictException, UnprocessableEntityException
from ..common.exceptions import ResourceNotFoundError
from .constants import InspectionStatus, Kind, ResponseType, RuleType
from .models import AcceptanceCriterion, ChecklistTemplate, Inspection
from .tolerance import criterion_clause, parse_decimal, range_order_error

FROZEN_FIELDS = ("rule_type", "unit", "nominal", "lower_limit", "upper_limit")
GATE_TABLE = "inspections_gates"
"""A gate points at a criterion but never judges against it, so it blocks deletion and not editing."""
TEMPLATES = "templates"
HOLDER_LABELS = {
    "inspections": "inspection records",
    "inspections_items": "checklist items",
    GATE_TABLE: "gates",
    "materials_receipts": "material records",
    "materials_pmi": "PMI tests",
    "as_built_records": "as-built records",
    TEMPLATES: "templates",
}


class CriterionNotFoundError(ResourceNotFoundError):
    public_detail = "Acceptance criterion not found."


async def get_criterion(db: AsyncSession, criterion_id: int, project_id: int | None = None) -> AcceptanceCriterion:
    """Missing and foreign-project criteria answer the same not-found, so other projects' criteria stay hidden."""
    c = await db.get(AcceptanceCriterion, criterion_id)
    if c is None or (project_id is not None and c.project_id != project_id):
        raise CriterionNotFoundError("No such criterion")
    return c


# --- holders -----------------------------------------------------------------------------------------


def holder_tables() -> list[Table]:
    own = AcceptanceCriterion.__tablename__
    return [t for name, t in sorted(Base.metadata.tables.items()) if name != own and "criterion_id" in t.c]


async def holders_of(db: AsyncSession, criterion_id: int) -> dict[str, int]:
    """Every table that points at the criterion, with the number of rows (templates are counted separately)."""
    found: dict[str, int] = {}
    for table in holder_tables():
        n = await db.scalar(select(func.count()).select_from(table).where(table.c.criterion_id == criterion_id))
        if n:
            found[table.name] = n
    return found


def _template_refs(template: ChecklistTemplate, criterion_id: int) -> int:
    if template.kind == Kind.ITP:
        return sum(1 for act in template.activities if act.get("criterion_id") == criterion_id)
    return sum(
        1 for section in template.sections for item in section.get("items", []) if item.get("criterion_id") == criterion_id
    )


async def template_refs(db: AsyncSession, criterion: AcceptanceCriterion) -> int:
    rows = await db.execute(select(ChecklistTemplate).where(ChecklistTemplate.project_id == criterion.project_id))
    return sum(_template_refs(t, criterion.id) for t in rows.scalars())


def _label(name: str) -> str:
    return HOLDER_LABELS.get(name, name)


# --- create, update, delete --------------------------------------------------------------------------


async def _code_taken(db: AsyncSession, project_id: int, code: str, *, except_id: int | None = None) -> bool:
    where = [AcceptanceCriterion.project_id == project_id, AcceptanceCriterion.code == code]
    if except_id is not None:
        where.append(AcceptanceCriterion.id != except_id)
    return bool(await db.scalar(select(AcceptanceCriterion.id).where(*where)))


async def create_criterion(db: AsyncSession, values: dict[str, Any], user_id: int) -> AcceptanceCriterion:
    error = range_order_error(values.get("rule_type"), values.get("lower_limit"), values.get("upper_limit"))
    if error:
        raise UnprocessableEntityException(error)
    if await _code_taken(db, values["project_id"], values["code"]):
        raise ConflictException(f"A criterion with code '{values['code']}' already exists on this project.")
    c = AcceptanceCriterion(created_by_id=user_id, **values)
    db.add(c)
    await db.commit()
    return c


async def update_criterion(db: AsyncSession, criterion: AcceptanceCriterion, changes: dict[str, Any]) -> None:
    """Partial update. The range-order check runs only when the same patch states the range rule and both limits;
    the freeze rule counts real changes only (re-sending a stored value is not a change)."""
    if changes.get("rule_type") == RuleType.RANGE.value and "lower_limit" in changes and "upper_limit" in changes:
        error = range_order_error(RuleType.RANGE.value, changes["lower_limit"], changes["upper_limit"])
        if error:
            raise UnprocessableEntityException(error)
    if "code" in changes and changes["code"] != criterion.code:
        if await _code_taken(db, criterion.project_id, changes["code"], except_id=criterion.id):
            raise ConflictException(f"A criterion with code '{changes['code']}' already exists on this project.")
    if any(k in changes and changes[k] != getattr(criterion, k) for k in FROZEN_FIELDS):
        judged = sum(n for table, n in (await holders_of(db, criterion.id)).items() if table != GATE_TABLE)
        if judged:
            raise ConflictException(
                f"{judged} record(s) are already judged against this criterion, so its rule, unit, nominal and limits "
                "are frozen. Create a new criterion and deactivate this one."
            )
    for key, value in changes.items():
        setattr(criterion, key, value)
    await db.commit()


async def delete_criterion(db: AsyncSession, criterion: AcceptanceCriterion) -> None:
    held = await holders_of(db, criterion.id)
    templates = await template_refs(db, criterion)
    if templates:
        held[TEMPLATES] = templates
    if held:
        listed = ", ".join(f"{n} {_label(name)}" for name, n in held.items())
        raise ConflictException(
            f"This criterion is still referenced by {listed}. Point those records at another criterion, or clear "
            "the active flag instead of deleting it."
        )
    await db.delete(criterion)
    await db.commit()


# --- references from templates and records -----------------------------------------------------------


async def check_template_refs(
    db: AsyncSession, project_id: int, sections: list[dict[str, Any]] | None, activities: list[dict[str, Any]] | None
) -> None:
    """Every criterion a template item or ITP activity names must belong to the template's project."""
    ids = {i["criterion_id"] for s in sections or [] for i in s.get("items", []) if i.get("criterion_id")}
    ids |= {a["criterion_id"] for a in activities or [] if a.get("criterion_id")}
    for criterion_id in sorted(ids):
        await get_criterion(db, criterion_id, project_id)


async def check_record_criterion(db: AsyncSession, project_id: int, criterion_id: int | None) -> None:
    if criterion_id is not None:
        await get_criterion(db, criterion_id, project_id)


async def check_record_edit(db: AsyncSession, inspection: Inspection, changes: dict[str, Any]) -> None:
    """An ordinary edit may not change the criterion or measured value while a result stands."""
    moved = [k for k in ("criterion_id", "measured_value") if k in changes and changes[k] != getattr(inspection, k)]
    if moved and inspection.status in (InspectionStatus.COMPLETED, InspectionStatus.CLOSED):
        raise UnprocessableEntityException("A result stands on this inspection; reopen it before changing its criterion.")
    if "criterion_id" in changes:
        await check_record_criterion(db, inspection.project_id, changes["criterion_id"])


def _snapshot_item(raw: dict[str, Any], criterion: AcceptanceCriterion) -> dict[str, Any]:
    """Numeric criterion: copy the limits (as numbers) and unit onto the item. Any other criterion leaves a
    pass/fail/N-A item and adds the criterion clause to its guidance."""
    item = dict(raw)
    rule = criterion.rule_type
    needs_low = rule in (RuleType.MINIMUM.value, RuleType.RANGE.value)
    needs_high = rule in (RuleType.MAXIMUM.value, RuleType.RANGE.value)
    low = parse_decimal(criterion.lower_limit) if needs_low else None
    high = parse_decimal(criterion.upper_limit) if needs_high else None
    if (needs_low or needs_high) and not (needs_low and low is None) and not (needs_high and high is None):
        item.update(
            response_type=ResponseType.NUMERIC.value,
            unit=criterion.unit or item.get("unit"),
            min_value=float(low) if low is not None else None,
            max_value=float(high) if high is not None else None,
        )
    else:
        clause = criterion_clause(criterion)
        item["guidance"] = f"{item['guidance']}\n{clause}" if item.get("guidance") else clause
    return item


async def snapshot_sections(db: AsyncSession, project_id: int, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The template sections with each criterion-linked item filled from its criterion, called just before the
    checklist items of a record are built. Sections without criteria come back unchanged."""
    cache: dict[int, AcceptanceCriterion] = {}
    out = []
    for section in sections:
        items = []
        for raw in section.get("items", []):
            criterion_id = raw.get("criterion_id")
            if criterion_id:
                if criterion_id not in cache:
                    cache[criterion_id] = await get_criterion(db, criterion_id, project_id)
                raw = _snapshot_item(raw, cache[criterion_id])
            items.append(raw)
        out.append({**section, "items": items})
    return out
