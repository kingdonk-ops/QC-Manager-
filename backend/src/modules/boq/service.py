"""Bills, positions, resource lines and the undo log. No FastAPI in here.

Every change to a bill's content goes through ``Change``: it snapshots the rows it is about to
touch, lets the caller change them, recomputes the bill (``calc``), and logs the before and after
snapshots as one ``Operation`` that ``undo``/``redo`` can replay.
"""

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..contacts.service import contact_names
from ..projects.models import Project
from . import calc
from .formula import FormulaError, evaluate
from .models import Assembly, AssemblyLine, Boq, Operation, Position, PositionResource, Resource
from .validation import VLine, VNode

FLOW: dict[str, set[str]] = {
    "draft": {"priced", "locked"},
    "priced": {"draft", "locked"},
    "locked": {"draft", "priced"},
}
MAX_OPERATIONS = 200
"""How many changes a bill remembers for undo."""

POSITION_FIELDS = (
    "id",
    "boq_id",
    "parent_id",
    "sort",
    "kind",
    "ordinal",
    "depth",
    "code",
    "short_text",
    "long_text",
    "unit",
    "quantity",
    "quantity_formula",
    "unit_rate",
    "total",
    "classification",
    "assembly_id",
)
LINE_FIELDS = ("id", "position_id", "resource_id", "factor", "waste_pct", "rate_override", "sort")
BOQ_FIELDS = ("name", "description", "overhead_pct", "profit_pct", "contingency_pct", "tax_pct")
DECIMALS = {"quantity", "unit_rate", "total", "factor", "waste_pct", "rate_override"} | {
    f for f in BOQ_FIELDS if f.endswith("_pct")
}


class BoqNotFoundError(ResourceNotFoundError):
    public_detail = "Bill of quantities not found."


class PositionNotFoundError(ResourceNotFoundError):
    public_detail = "Position not found."


class CatalogResourceNotFoundError(ResourceNotFoundError):
    public_detail = "Resource not found."


class AssemblyNotFoundError(ResourceNotFoundError):
    public_detail = "Assembly not found."


class BoqLockedError(ValidationError):
    public_detail = "This bill is locked. Unlock it to make changes."


class BoqRuleError(ValidationError):
    """A refused change. The message says why and is shown to the caller, so it never names other rows."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        setattr(self, "public_detail", message)  # noqa: B010 - per instance, over the class default


class NothingToUndoError(ValidationError):
    public_detail = "There is nothing to undo or redo."


# --- loading ---------------------------------------------------------------------------------------------


async def get_boq(db: AsyncSession, boq_id: int) -> Boq:
    boq = await db.get(Boq, boq_id)
    if boq is None:
        raise BoqNotFoundError(str(boq_id))
    return boq


async def get_position(db: AsyncSession, position_id: int) -> Position:
    position = await db.get(Position, position_id)
    if position is None:
        raise PositionNotFoundError(str(position_id))
    return position


def assert_editable(boq: Boq) -> None:
    if boq.status == "locked":
        raise BoqLockedError(str(boq.id))


async def positions_of(db: AsyncSession, boq_id: int) -> list[Position]:
    return list((await db.execute(select(Position).where(Position.boq_id == boq_id))).scalars())


async def lines_of(db: AsyncSession, position_ids: Iterable[int]) -> dict[int, list[PositionResource]]:
    ids = list(position_ids)
    out: dict[int, list[PositionResource]] = defaultdict(list)
    if not ids:
        return out
    rows = await db.execute(
        select(PositionResource)
        .where(PositionResource.position_id.in_(ids))
        .order_by(PositionResource.sort, PositionResource.id)
    )
    for line in rows.scalars():
        out[line.position_id].append(line)
    return out


async def resources_by_id(db: AsyncSession, ids: Iterable[int]) -> dict[int, Resource]:
    ids = set(ids)
    if not ids:
        return {}
    return {r.id: r for r in (await db.execute(select(Resource).where(Resource.id.in_(ids)))).scalars()}


def _effective(line: PositionResource, resource: Resource | None) -> Decimal:
    if line.rate_override is not None:
        return line.rate_override
    return resource.rate if resource else Decimal(0)


class Loaded:
    """A bill's rows, lines and resources, with the calculation done."""

    def __init__(
        self,
        positions: list[Position],
        lines: dict[int, list[PositionResource]],
        resources: dict[int, Resource],
    ) -> None:
        self.positions = positions
        self.lines = lines
        self.resources = resources
        self.nodes = [
            calc.Node(
                id=p.id,
                parent_id=p.parent_id,
                sort=p.sort,
                kind=p.kind,
                quantity=p.quantity,
                unit_rate=p.unit_rate,
                lines=[
                    calc.Line(line.factor, _effective(line, resources.get(line.resource_id)), line.waste_pct)
                    for line in lines.get(p.id, [])
                ],
            )
            for p in positions
        ]
        self.computed = calc.rollup(self.nodes)
        self.order = [n.id for n, _, _ in calc.depth_first(self.nodes)]
        self.by_id = {p.id: p for p in positions}


async def load(db: AsyncSession, boq_id: int) -> Loaded:
    positions = await positions_of(db, boq_id)
    lines = await lines_of(db, [p.id for p in positions])
    resources = await resources_by_id(db, {line.resource_id for ls in lines.values() for line in ls})
    return Loaded(positions, lines, resources)


async def recalc(db: AsyncSession, boq: Boq) -> Loaded:
    """Write the derived fields (ordinals, depths, rates, totals) back to the rows."""
    loaded = await load(db, boq.id)
    for p in loaded.positions:
        c = loaded.computed[p.id]
        p.ordinal, p.depth, p.total = c.ordinal, c.depth, c.total
        if loaded.lines.get(p.id):
            p.unit_rate = c.unit_rate
    net = calc.net_total(loaded.nodes, loaded.computed)
    totals = calc.markups(net, boq.overhead_pct, boq.profit_pct, boq.contingency_pct, boq.tax_pct)
    boq.net_total, boq.grand_total = totals["net_total"], totals["grand_total"]
    await db.flush()
    return loaded


def _line_read(line: PositionResource, resource: Resource | None) -> dict[str, Any]:
    rate = _effective(line, resource)
    return {
        "id": line.id,
        "resource_id": line.resource_id,
        "code": resource.code if resource else "?",
        "name": resource.name if resource else "(deleted resource)",
        "type": resource.type if resource else "material",
        "unit": resource.unit if resource else "",
        "factor": line.factor,
        "waste_pct": line.waste_pct,
        "rate_override": line.rate_override,
        "catalog_rate": resource.rate if resource else Decimal(0),
        "rate": rate,
        "cost": calc.rate4(calc.Line(line.factor, rate, line.waste_pct).cost),
    }


async def detail(db: AsyncSession, boq: Boq, loaded: Loaded | None = None) -> dict[str, Any]:
    loaded = loaded or await load(db, boq.id)
    project = await db.get(Project, boq.project_id)
    net = calc.net_total(loaded.nodes, loaded.computed)
    totals = calc.markups(net, boq.overhead_pct, boq.profit_pct, boq.contingency_pct, boq.tax_pct)
    undo = await db.scalar(
        select(Operation.label)
        .where(Operation.boq_id == boq.id, Operation.undone.is_(False))
        .order_by(Operation.seq.desc())
        .limit(1)
    )
    redo = await db.scalar(
        select(Operation.label).where(Operation.boq_id == boq.id, Operation.undone.is_(True)).order_by(Operation.seq).limit(1)
    )
    positions = []
    for pid in loaded.order:
        p, c = loaded.by_id[pid], loaded.computed[pid]
        positions.append(
            {
                "id": p.id,
                "parent_id": p.parent_id,
                "kind": p.kind,
                "ordinal": c.ordinal,
                "depth": c.depth,
                "sort": p.sort,
                "code": p.code,
                "short_text": p.short_text,
                "long_text": p.long_text,
                "unit": p.unit,
                "quantity": p.quantity,
                "quantity_formula": p.quantity_formula,
                "unit_rate": c.unit_rate,
                "total": c.total,
                "classification": p.classification,
                "assembly_id": p.assembly_id,
                "has_children": c.has_children,
                "resources": [_line_read(line, loaded.resources.get(line.resource_id)) for line in loaded.lines.get(p.id, [])],
            }
        )
    return {
        "id": boq.id,
        "project_id": boq.project_id,
        "name": boq.name,
        "description": boq.description,
        "status": boq.status,
        "currency": boq.currency,
        "net_total": totals["net_total"],
        "grand_total": totals["grand_total"],
        "created_at": boq.created_at,
        "updated_at": boq.updated_at,
        "classification_standard": project.classification_standard if project else None,
        "overhead_pct": boq.overhead_pct,
        "profit_pct": boq.profit_pct,
        "contingency_pct": boq.contingency_pct,
        "tax_pct": boq.tax_pct,
        "totals": totals,
        "can_undo": undo is not None,
        "can_redo": redo is not None,
        "undo_label": undo,
        "redo_label": redo,
        "positions": positions,
    }


def validation_bill(loaded: Loaded) -> list[VNode]:
    bill = []
    for pid in loaded.order:
        p, c = loaded.by_id[pid], loaded.computed[pid]
        bill.append(
            VNode(
                id=p.id,
                parent_id=p.parent_id,
                kind=p.kind,
                ordinal=c.ordinal,
                depth=c.depth,
                code=p.code,
                short_text=p.short_text,
                unit=p.unit,
                quantity=p.quantity,
                unit_rate=c.unit_rate,
                total=c.total,
                classification=p.classification,
                has_children=c.has_children,
                lines=[
                    VLine(
                        resource_id=line.resource_id,
                        resource_code=(r.code if (r := loaded.resources.get(line.resource_id)) else "?"),
                        rate=_effective(line, r),
                        catalog_rate=r.rate if r else Decimal(0),
                        rate_override=line.rate_override,
                    )
                    for line in loaded.lines.get(p.id, [])
                ],
            )
        )
    return bill


# --- the undo log ----------------------------------------------------------------------------------------


def _dump(obj: Any, fields: Iterable[str]) -> dict[str, Any]:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = str(v) if isinstance(v, Decimal) else v
    return out


def _load_value(field: str, value: Any) -> Any:
    return Decimal(value) if field in DECIMALS and value is not None else value


async def capture(db: AsyncSession, boq: Boq, ids: Iterable[int], *, with_boq: bool = False) -> dict[str, Any]:
    """The listed positions (those that exist) with their resource lines, and optionally the bill's fields."""
    ids = set(ids)
    rows = (
        list((await db.execute(select(Position).where(Position.boq_id == boq.id, Position.id.in_(ids)))).scalars())
        if ids
        else []
    )
    lines = await lines_of(db, [p.id for p in rows])
    return {
        "positions": {
            str(p.id): {**_dump(p, POSITION_FIELDS), "lines": [_dump(line, LINE_FIELDS) for line in lines.get(p.id, [])]}
            for p in rows
        },
        "boq": _dump(boq, BOQ_FIELDS) if with_boq else None,
    }


async def _restore(db: AsyncSession, boq: Boq, target: dict[str, Any], other: dict[str, Any]) -> None:
    """Make the rows look like ``target``: rows only in ``other`` go, the rest get ``target``'s values."""
    wanted: dict[str, dict[str, Any]] = target["positions"]
    gone = [int(i) for i in other["positions"] if i not in wanted]
    if gone:
        await db.execute(delete(Position).where(Position.boq_id == boq.id, Position.id.in_(gone)))
        await db.flush()
    live_resources = set(
        (
            await db.execute(
                select(Resource.id).where(
                    Resource.id.in_({line["resource_id"] for row in wanted.values() for line in row["lines"]} or {0})
                )
            )
        ).scalars()
    )
    existing = {p.id for p in await positions_of(db, boq.id)}
    for row in sorted(wanted.values(), key=lambda r: r["depth"]):
        position = await db.get(Position, row["id"])
        if position is None:
            if row["parent_id"] is not None and row["parent_id"] not in existing:
                row = {**row, "parent_id": None}
            position = Position(boq_id=boq.id)
            position.id = row["id"]
            db.add(position)
        for f in POSITION_FIELDS:
            if f not in ("id", "boq_id"):
                setattr(position, f, _load_value(f, row[f]))
        await db.flush()
        existing.add(position.id)
        keep = {line["id"] for line in row["lines"]}
        await db.execute(
            delete(PositionResource).where(PositionResource.position_id == position.id, PositionResource.id.not_in(keep or {0}))
        )
        for data in row["lines"]:
            if data["resource_id"] not in live_resources:
                continue
            line = await db.get(PositionResource, data["id"])
            if line is None:
                line = PositionResource(position_id=position.id, resource_id=data["resource_id"])
                line.id = data["id"]
                db.add(line)
            for f in LINE_FIELDS:
                if f != "id":
                    setattr(line, f, _load_value(f, data[f]))
        await db.flush()
    if target.get("boq"):
        for f, v in target["boq"].items():
            setattr(boq, f, _load_value(f, v))


async def log_operation(
    db: AsyncSession, boq: Boq, label: str, before: dict[str, Any], after: dict[str, Any], user_id: int | None
) -> None:
    await db.execute(delete(Operation).where(Operation.boq_id == boq.id, Operation.undone.is_(True)))
    seq = (await db.scalar(select(func.max(Operation.seq)).where(Operation.boq_id == boq.id))) or 0
    db.add(Operation(boq_id=boq.id, seq=seq + 1, label=label[:200], before=before, after=after, user_id=user_id))
    if seq + 1 > MAX_OPERATIONS:
        await db.execute(delete(Operation).where(Operation.boq_id == boq.id, Operation.seq <= seq + 1 - MAX_OPERATIONS))


class Change:
    """``async with Change(db, boq, "Edit 1.2", ids, user_id) as ch: ...; ch.touch(new_id)``.

    Snapshots ``ids`` on entry; on a clean exit snapshots them again (with any ``touch``ed ids),
    recalculates, logs the operation and commits.
    """

    def __init__(
        self, db: AsyncSession, boq: Boq, label: str, ids: Iterable[int], user_id: int | None, *, with_boq: bool = False
    ) -> None:
        assert_editable(boq)
        self.db, self.boq, self.label, self.user_id, self.with_boq = db, boq, label, user_id, with_boq
        self.ids = set(ids)
        self.before: dict[str, Any] = {}
        self.loaded: Loaded | None = None

    def touch(self, *ids: int) -> None:
        self.ids.update(ids)

    async def __aenter__(self) -> "Change":
        self.before = await capture(self.db, self.boq, self.ids, with_boq=self.with_boq)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            await self.db.rollback()
            return
        await self.db.flush()
        self.loaded = await recalc(self.db, self.boq)
        after = await capture(self.db, self.boq, self.ids, with_boq=self.with_boq)
        await log_operation(self.db, self.boq, self.label, self.before, after, self.user_id)
        await self.db.commit()


async def undo(db: AsyncSession, boq: Boq) -> None:
    assert_editable(boq)
    op = await db.scalar(
        select(Operation).where(Operation.boq_id == boq.id, Operation.undone.is_(False)).order_by(Operation.seq.desc()).limit(1)
    )
    if op is None:
        raise NothingToUndoError("undo")
    await _restore(db, boq, op.before, op.after)
    op.undone = True
    await recalc(db, boq)
    await db.commit()


async def redo(db: AsyncSession, boq: Boq) -> None:
    assert_editable(boq)
    op = await db.scalar(
        select(Operation).where(Operation.boq_id == boq.id, Operation.undone.is_(True)).order_by(Operation.seq).limit(1)
    )
    if op is None:
        raise NothingToUndoError("redo")
    await _restore(db, boq, op.after, op.before)
    op.undone = False
    await recalc(db, boq)
    await db.commit()


# --- structure -------------------------------------------------------------------------------------------


async def _siblings(db: AsyncSession, boq_id: int, parent_id: int | None) -> list[Position]:
    where = Position.parent_id.is_(None) if parent_id is None else Position.parent_id == parent_id
    return list(
        (await db.execute(select(Position).where(Position.boq_id == boq_id, where).order_by(Position.sort, Position.id)))
        .scalars()
        .all()
    )


async def _check_parent(db: AsyncSession, boq: Boq, parent_id: int | None, kind: str) -> None:
    if parent_id is None:
        return
    parent = await db.get(Position, parent_id)
    if parent is None or parent.boq_id != boq.id:
        raise BoqRuleError("The parent isn't in this bill.")
    if kind == "section" and parent.kind != "section":
        raise BoqRuleError("A section can only sit at the top level or inside another section.")


def _apply_fields(position: Position, values: dict[str, Any], has_lines: bool) -> None:
    if "quantity_formula" in values:
        formula = (values.pop("quantity_formula") or "").strip()
        if formula:
            try:
                values["quantity"] = evaluate(formula)
            except FormulaError as exc:
                raise BoqRuleError(f"Quantity formula: {exc}") from exc
            if abs(values["quantity"]) >= 10**13:
                raise BoqRuleError("Quantity formula: the result is too large")
            values["quantity"] = values["quantity"].quantize(Decimal("0.0001"))
            position.quantity_formula = formula
        else:
            position.quantity_formula = None
    elif "quantity" in values:
        position.quantity_formula = None
    if "unit_rate" in values and has_lines and values["unit_rate"] != position.unit_rate:
        raise BoqRuleError("This rate comes from the position's resources. Change those, or remove them first.")
    for key, value in values.items():
        setattr(position, key, value.value if hasattr(value, "value") else value)


async def _place(
    db: AsyncSession, boq_id: int, parent_id: int | None, before_id: int | None, after_id: int | None, ids: list[int]
) -> list[Position]:
    """Renumber the parent's children with ``ids`` (already children) placed before/after a sibling."""
    siblings = await _siblings(db, boq_id, parent_id)
    order = [s.id for s in siblings if s.id not in ids]
    if before_id in order:
        at = order.index(before_id)
    elif after_id in order:
        at = order.index(after_id) + 1
    else:
        at = len(order)
    order[at:at] = ids
    by_id = {s.id: s for s in siblings}
    for i, sid in enumerate(order):
        if sid in by_id:
            by_id[sid].sort = i
    return siblings


async def sibling_ids(db: AsyncSession, boq_id: int, parent_id: int | None) -> list[int]:
    return [s.id for s in await _siblings(db, boq_id, parent_id)]


async def create_positions(
    db: AsyncSession,
    boq: Boq,
    parent_id: int | None,
    rows: list[dict[str, Any]],
    *,
    before_id: int | None = None,
    after_id: int | None = None,
    user_id: int | None,
    label: str,
) -> list[int]:
    for row in rows:
        await _check_parent(db, boq, parent_id, str(row.get("kind", "position")))
    async with Change(db, boq, label, await sibling_ids(db, boq.id, parent_id), user_id) as change:
        new_ids = []
        for row in rows:
            row = dict(row)
            kind = str(row.pop("kind", "position"))
            position = Position(boq_id=boq.id, parent_id=parent_id, kind=kind, sort=10**6)
            _apply_fields(position, {k: v for k, v in row.items() if v is not None}, False)
            position.short_text = position.short_text or ""
            db.add(position)
            await db.flush()
            new_ids.append(position.id)
        await _place(db, boq.id, parent_id, before_id, after_id, new_ids)
        change.touch(*new_ids)
    return new_ids


async def update_position(db: AsyncSession, boq: Boq, position: Position, values: dict[str, Any], user_id: int | None) -> None:
    if values.get("kind") == "section" and position.kind != "section" and position.parent_id:
        await _check_parent(db, boq, position.parent_id, "section")
    has_lines = bool((await lines_of(db, [position.id])).get(position.id))
    field = next(iter(values), "row")
    async with Change(db, boq, f"Edit {field.replace('_', ' ')} of {position.ordinal}", [position.id], user_id):
        _apply_fields(position, values, has_lines)


async def delete_position(db: AsyncSession, boq: Boq, position: Position, user_id: int | None) -> None:
    loaded = await load(db, boq.id)
    subtree = {position.id} | calc.descendants(loaded.nodes, position.id)
    async with Change(db, boq, f"Delete {position.ordinal} {position.short_text}".strip(), subtree, user_id):
        await db.execute(delete(Position).where(Position.id == position.id))


async def move_position(
    db: AsyncSession, boq: Boq, position: Position, parent_id: int | None, before_id: int | None, user_id: int | None
) -> None:
    if parent_id is not None:
        loaded = await load(db, boq.id)
        if parent_id == position.id or parent_id in calc.descendants(loaded.nodes, position.id):
            raise BoqRuleError("A row can't move inside itself.")
    await _check_parent(db, boq, parent_id, position.kind)
    old_parent = position.parent_id
    ids = {position.id, *await sibling_ids(db, boq.id, old_parent), *await sibling_ids(db, boq.id, parent_id)}
    async with Change(db, boq, f"Move {position.ordinal}", ids, user_id):
        position.parent_id = parent_id
        await db.flush()
        await _place(db, boq.id, parent_id, before_id, None, [position.id])
        if old_parent != parent_id:
            for i, s in enumerate(await _siblings(db, boq.id, old_parent)):
                s.sort = i


async def update_boq(db: AsyncSession, boq: Boq, values: dict[str, Any], user_id: int | None) -> None:
    label = "Change " + ", ".join(k.replace("_", " ") for k in values)
    async with Change(db, boq, label, [], user_id, with_boq=True):
        for key, value in values.items():
            setattr(boq, key, value)


# --- resource lines and assemblies ---------------------------------------------------------------------------


async def visible_resource(db: AsyncSession, resource_id: int, project_id: int | None) -> Resource:
    resource = await db.get(Resource, resource_id)
    if resource is None or resource.project_id not in (None, project_id):
        raise CatalogResourceNotFoundError(str(resource_id))
    return resource


async def for_project(db: AsyncSession, resource: Resource, project_id: int) -> Resource:
    """The project's override of a global resource, if it has one; otherwise the resource itself."""
    if resource.project_id is None:
        override = await db.scalar(
            select(Resource).where(Resource.project_id == project_id, Resource.base_id == resource.id).limit(1)
        )
        if override is not None:
            return override
    return resource


async def add_line(db: AsyncSession, boq: Boq, position: Position, values: dict[str, Any], user_id: int | None) -> None:
    resource = await for_project(db, await visible_resource(db, values["resource_id"], boq.project_id), boq.project_id)
    if position.kind == "section":
        raise BoqRuleError("Sections total their positions; add resources to a position.")
    async with Change(db, boq, f"Add {resource.code} to {position.ordinal}", [position.id], user_id):
        count = len((await lines_of(db, [position.id])).get(position.id, []))
        db.add(
            PositionResource(
                position_id=position.id,
                resource_id=resource.id,
                factor=values.get("factor", Decimal(1)),
                waste_pct=values.get("waste_pct", Decimal(0)),
                rate_override=values.get("rate_override"),
                sort=count,
            )
        )


async def get_line(db: AsyncSession, position: Position, line_id: int) -> PositionResource:
    line = await db.get(PositionResource, line_id)
    if line is None or line.position_id != position.id:
        raise CatalogResourceNotFoundError(str(line_id))
    return line


async def update_line(
    db: AsyncSession, boq: Boq, position: Position, line: PositionResource, values: dict[str, Any], user_id: int | None
) -> None:
    async with Change(db, boq, f"Edit a resource of {position.ordinal}", [position.id], user_id):
        for key, value in values.items():
            setattr(line, key, value)


async def delete_line(db: AsyncSession, boq: Boq, position: Position, line: PositionResource, user_id: int | None) -> None:
    async with Change(db, boq, f"Remove a resource from {position.ordinal}", [position.id], user_id):
        await db.delete(line)
        await db.flush()
        remaining = (await lines_of(db, [position.id])).get(position.id, [])
        if not remaining:
            position.unit_rate = None


async def get_assembly(db: AsyncSession, assembly_id: int, project_id: int | None = None) -> Assembly:
    assembly = await db.get(Assembly, assembly_id)
    if assembly is None or (project_id is not None and assembly.project_id not in (None, project_id)):
        raise AssemblyNotFoundError(str(assembly_id))
    return assembly


async def assembly_lines(db: AsyncSession, assembly_ids: Iterable[int]) -> dict[int, list[AssemblyLine]]:
    ids = list(assembly_ids)
    out: dict[int, list[AssemblyLine]] = defaultdict(list)
    if ids:
        rows = await db.execute(
            select(AssemblyLine).where(AssemblyLine.assembly_id.in_(ids)).order_by(AssemblyLine.sort, AssemblyLine.id)
        )
        for line in rows.scalars():
            out[line.assembly_id].append(line)
    return out


async def read_assemblies(db: AsyncSession, assemblies: list[Assembly]) -> list[dict[str, Any]]:
    lines = await assembly_lines(db, [a.id for a in assemblies])
    resources = await resources_by_id(db, {line.resource_id for ls in lines.values() for line in ls})
    out = []
    for a in assemblies:
        read_lines: list[dict[str, Any]] = []
        for line in lines.get(a.id, []):
            r = resources.get(line.resource_id)
            rate = r.rate if r else Decimal(0)
            read_lines.append(
                {
                    "id": line.id,
                    "resource_id": line.resource_id,
                    "code": r.code if r else "?",
                    "name": r.name if r else "(deleted resource)",
                    "type": r.type if r else "material",
                    "unit": r.unit if r else "",
                    "rate": rate,
                    "factor": line.factor,
                    "waste_pct": line.waste_pct,
                    "cost": calc.rate4(calc.Line(line.factor, rate, line.waste_pct).cost),
                }
            )
        out.append(
            {
                "id": a.id,
                "code": a.code,
                "name": a.name,
                "unit": a.unit,
                "description": a.description,
                "classification": a.classification,
                "project_id": a.project_id,
                "unit_rate": calc.rate4(sum((Decimal(line["cost"]) for line in read_lines), Decimal(0))),
                "lines": read_lines,
            }
        )
    return out


async def save_assembly_lines(db: AsyncSession, assembly: Assembly, lines: list[dict[str, Any]]) -> None:
    for line in lines:
        await visible_resource(db, line["resource_id"], assembly.project_id)
    await db.execute(delete(AssemblyLine).where(AssemblyLine.assembly_id == assembly.id))
    for i, line in enumerate(lines):
        db.add(
            AssemblyLine(
                assembly_id=assembly.id,
                resource_id=line["resource_id"],
                factor=line["factor"],
                waste_pct=line["waste_pct"],
                sort=i,
            )
        )


async def apply_assembly(
    db: AsyncSession, boq: Boq, position: Position, assembly_id: int, replace: bool, user_id: int | None
) -> None:
    assembly = await get_assembly(db, assembly_id, boq.project_id)
    if position.kind == "section":
        raise BoqRuleError("Apply an assembly to a position, not a section.")
    recipe = (await assembly_lines(db, [assembly.id])).get(assembly.id, [])
    async with Change(db, boq, f"Apply {assembly.code} to {position.ordinal}", [position.id], user_id):
        existing = (await lines_of(db, [position.id])).get(position.id, [])
        if replace:
            for line in existing:
                await db.delete(line)
            existing = []
        for i, step in enumerate(recipe, start=len(existing)):
            resource = await for_project(db, await visible_resource(db, step.resource_id, boq.project_id), boq.project_id)
            db.add(
                PositionResource(
                    position_id=position.id,
                    resource_id=resource.id,
                    factor=step.factor,
                    waste_pct=step.waste_pct,
                    sort=i,
                )
            )
        position.assembly_id = assembly.id
        position.unit = position.unit or assembly.unit or None
        position.short_text = position.short_text or assembly.name
        position.long_text = position.long_text or assembly.description
        position.classification = position.classification or assembly.classification


# --- catalog --------------------------------------------------------------------------------------------------


def resource_scope(project_id: int | None) -> Any:
    """Global resources (minus those the project overrides) and the project's own."""
    if project_id is None:
        return Resource.project_id.is_(None)
    overridden = select(Resource.base_id).where(Resource.project_id == project_id, Resource.base_id.is_not(None))
    return or_(
        Resource.project_id == project_id,
        (Resource.project_id.is_(None)) & Resource.id.not_in(overridden),
    )


async def read_resources(db: AsyncSession, resources: list[Resource]) -> list[dict[str, Any]]:
    ids = {r.supplier_contact_id for r in resources if r.supplier_contact_id}
    names: dict[int, str] = {}
    if ids:
        names = await contact_names(db, ids)
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "type": r.type,
            "unit": r.unit,
            "rate": r.rate,
            "currency": r.currency,
            "trade": r.trade,
            "supplier_contact_id": r.supplier_contact_id,
            "supplier_name": names.get(r.supplier_contact_id) if r.supplier_contact_id else None,
            "notes": r.notes,
            "project_id": r.project_id,
            "base_id": r.base_id,
        }
        for r in resources
    ]


async def get_resource(db: AsyncSession, resource_id: int) -> Resource:
    resource = await db.get(Resource, resource_id)
    if resource is None:
        raise CatalogResourceNotFoundError(str(resource_id))
    return resource


async def check_base(db: AsyncSession, base_id: int | None, project_id: int | None) -> None:
    if base_id is None:
        return
    base = await db.get(Resource, base_id)
    if base is None or base.project_id is not None:
        raise BoqRuleError("base_id must be a resource from the global catalog.")
    if project_id is None:
        raise BoqRuleError("An override belongs to a project: give project_id.")


# --- import -----------------------------------------------------------------------------------------------------


async def import_rows(db: AsyncSession, boq: Boq, rows: list[Any], *, replace: bool, user_id: int | None, label: str) -> int:
    """Insert ``exchange.ImportRow``s (already linked) below what's there, or in place of it."""
    existing = await positions_of(db, boq.id)
    top = [p for p in existing if p.parent_id is None]
    async with Change(db, boq, label, [p.id for p in (existing if replace else top)], user_id) as change:
        if replace:
            await db.execute(delete(Position).where(Position.boq_id == boq.id))
            top = []
        next_sort = max((p.sort for p in top), default=-1) + 1
        created: list[int] = []
        counts: dict[int, int] = defaultdict(int)
        for row in rows:
            parent_id = created[row.parent] if row.parent is not None else None
            if parent_id is None:
                sort, next_sort = next_sort, next_sort + 1
            else:
                sort = counts[parent_id]
                counts[parent_id] += 1
            position = Position(boq_id=boq.id, parent_id=parent_id, kind=row.kind, sort=sort)
            for key, value in row.fields.items():
                setattr(position, key, value)
            position.short_text = position.short_text or ""
            db.add(position)
            await db.flush()
            created.append(position.id)
        change.touch(*created)
    return len(created)
