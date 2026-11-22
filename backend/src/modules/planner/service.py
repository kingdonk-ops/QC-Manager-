"""Work plans, packs, crews, readiness and the board. No FastAPI imports."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.constants import CollectionKind
from ..asset_tree.models import AssetCollection, AssetCollectionMember, AssetNode
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from .constants import MAX_BOARD_DAYS, PACK_FLOW, PLAN_FLOW, ConstraintStatus, PackStatus, PrerequisiteStatus, Severity
from .models import Crew, DailyAssignment, PlanConstraint, Prerequisite, WorkPack, WorkPackLine, WorkPlan
from .readiness import Finding, ReadinessContext, evaluate, register_readiness
from .readiness import actuals as collect_actuals
from .schemas import (
    AssignmentRead,
    ConstraintRead,
    CrewRead,
    PackLineRead,
    PackRead,
    PlanRead,
    PlanVsActual,
    PlanVsActualRow,
    PrerequisiteRead,
    ReadinessFindingRead,
)

ZERO = Decimal(0)


class PlanNotFound(ResourceNotFoundError):
    public_detail = "Work plan not found."


class PackNotFound(ResourceNotFoundError):
    public_detail = "Work pack not found."


class CrewNotFound(ResourceNotFoundError):
    public_detail = "Crew not found."


class ConstraintNotFound(ResourceNotFoundError):
    public_detail = "Constraint not found."


class PrerequisiteNotFound(ResourceNotFoundError):
    public_detail = "Prerequisite not found."


class AssignmentNotFound(ResourceNotFoundError):
    public_detail = "Assignment not found."


class PlanRuleError(ValidationError):
    public_detail = "That change breaks the plan's rules."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


def plan_link(plan: WorkPlan) -> str:
    return f"/planner?project={plan.project_id}&plan={plan.id}"


def pack_link(pack: WorkPack) -> str:
    return f"/planner?project={pack.project_id}&plan={pack.plan_id}&pack={pack.id}"


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    clean = {i for i in ids if i}
    if not clean:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(clean)))).tuples().all())


async def nodes_by_id(db: AsyncSession, ids: set[int]) -> dict[int, AssetNode]:
    if not ids:
        return {}
    return {n.id: n for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(ids)))).scalars()}


# --- lookups -------------------------------------------------------------------------------------------


async def get_plan(db: AsyncSession, plan_id: int) -> WorkPlan:
    plan = await db.get(WorkPlan, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    return plan


async def get_pack(db: AsyncSession, pack_id: int) -> WorkPack:
    pack = await db.get(WorkPack, pack_id)
    if pack is None:
        raise PackNotFound(str(pack_id))
    return pack


async def get_crew(db: AsyncSession, crew_id: int, project_id: int | None = None) -> Crew:
    crew = await db.get(Crew, crew_id)
    if crew is None or (project_id is not None and crew.project_id != project_id):
        raise CrewNotFound(str(crew_id))
    return crew


async def get_constraint(db: AsyncSession, constraint_id: int) -> PlanConstraint:
    row = await db.get(PlanConstraint, constraint_id)
    if row is None:
        raise ConstraintNotFound(str(constraint_id))
    return row


async def resolve_anchor(db: AsyncSession, project_id: int, node_id: int | None, item_id: int | None = None) -> AssetNode:
    """The work anchor for a picked node or item. ``NoWorkAnchor`` (422) when its path has none."""
    if item_id:
        item = await tree.get_item(db, item_id, project_id)
        if item.work_anchor_id:
            return await tree.get_node(db, item.work_anchor_id, project_id)
        node_id = item.node_id
    if not node_id:
        raise tree.NoWorkAnchor()
    await tree.get_node(db, node_id, project_id)
    return await tree.work_anchor_for(db, node_id)


# --- crews ---------------------------------------------------------------------------------------------


async def read_crews(db: AsyncSession, crews: list[Crew]) -> list[dict[str, Any]]:
    names = await user_names(db, {c.supervisor_id for c in crews})
    return [
        CrewRead.model_validate(c)
        .model_copy(update={"supervisor_name": names.get(c.supervisor_id or 0), "headcount": len(c.members or [])})
        .model_dump(mode="json")
        for c in crews
    ]


# --- plans ---------------------------------------------------------------------------------------------


async def _check_activities(db: AsyncSession, project_id: int, ids: list[int]) -> None:
    """Activity links are checked only while ``schedule`` is on; otherwise they're kept as given."""
    if not ids or not await is_enabled(db, "schedule", project_id):
        return
    try:
        from ..schedule.models import Activity  # noqa: PLC0415 - optional module
    except ImportError:  # pragma: no cover - schedule removed from the deployment
        return
    found = set(
        (await db.execute(select(Activity.id).where(Activity.project_id == project_id, Activity.id.in_(ids)))).scalars()
    )
    missing = sorted(set(ids) - found)
    if missing:
        raise PlanRuleError(f"Programme activities not found in this project: {', '.join(map(str, missing))}.")


async def create_plan(db: AsyncSession, values: dict[str, Any], user_id: int) -> WorkPlan:
    project_id = values["project_id"]
    await _check_activities(db, project_id, values.get("schedule_activity_ids") or [])
    code = await next_reference(db, "WP", project_id)
    collection = AssetCollection(
        project_id=project_id,
        kind=CollectionKind.WORK_PLAN.value,
        code=code,
        name=values["title"][:200],
        window_start=values["window_start"],
        window_end=values["window_end"],
    )
    db.add(collection)
    await db.flush()
    plan = WorkPlan(code=code, collection_id=collection.id, owner_id=values.pop("owner_id", None) or user_id, **values)
    db.add(plan)
    await db.flush()
    await record_transition(db, "work_plan", plan.id, None, plan.status, user_id)
    return plan


async def update_plan(db: AsyncSession, plan: WorkPlan, values: dict[str, Any]) -> None:
    if plan.status in ("closed", "cancelled"):
        raise PlanRuleError("A closed or cancelled plan can't change.")
    if "schedule_activity_ids" in values and values["schedule_activity_ids"] is not None:
        await _check_activities(db, plan.project_id, values["schedule_activity_ids"])
    for key, value in values.items():
        if value is not None or key in ("client_ref", "notes", "owner_id"):
            setattr(plan, key, value)
    if plan.window_end < plan.window_start:
        raise PlanRuleError("The window ends before it starts.")
    if plan.collection_id:
        collection = await db.get(AssetCollection, plan.collection_id)
        if collection is not None:
            collection.name = plan.title[:200]
            collection.window_start, collection.window_end = plan.window_start, plan.window_end
    await db.flush()


async def sync_collection(db: AsyncSession, plan: WorkPlan) -> None:
    """Keep the plan's ``work_plan`` collection equal to the work anchors its packs list."""
    if not plan.collection_id:
        return
    anchors = set(
        (
            await db.execute(
                select(WorkPackLine.anchor_id)
                .join(WorkPack, WorkPack.id == WorkPackLine.pack_id)
                .where(WorkPack.plan_id == plan.id)
            )
        ).scalars()
    )
    await db.execute(delete(AssetCollectionMember).where(AssetCollectionMember.collection_id == plan.collection_id))
    db.add_all([AssetCollectionMember(collection_id=plan.collection_id, node_id=a) for a in sorted(anchors)])
    await db.flush()


async def read_plans(db: AsyncSession, plans: list[WorkPlan]) -> list[dict[str, Any]]:
    ids = [p.id for p in plans]
    stats: dict[int, tuple[int, int, Decimal]] = {}
    if ids:
        packs = dict(
            (
                await db.execute(
                    select(WorkPack.plan_id, func.count()).where(WorkPack.plan_id.in_(ids)).group_by(WorkPack.plan_id)
                )
            )
            .tuples()
            .all()
        )
        lines = (
            await db.execute(
                select(
                    WorkPack.plan_id, func.count(func.distinct(WorkPackLine.anchor_id)), func.sum(WorkPackLine.planned_hours)
                )
                .join(WorkPack, WorkPack.id == WorkPackLine.pack_id)
                .where(WorkPack.plan_id.in_(ids))
                .group_by(WorkPack.plan_id)
            )
        ).tuples()
        line_stats = {pid: (n, h or ZERO) for pid, n, h in lines}
        stats = {pid: (packs.get(pid, 0), *line_stats.get(pid, (0, ZERO))) for pid in ids}
    return [
        PlanRead.model_validate(p)
        .model_copy(
            update={
                "pack_count": stats.get(p.id, (0, 0, ZERO))[0],
                "anchor_count": stats.get(p.id, (0, 0, ZERO))[1],
                "planned_hours": stats.get(p.id, (0, 0, ZERO))[2],
            }
        )
        .model_dump(mode="json")
        for p in plans
    ]


async def transition_plan(db: AsyncSession, plan: WorkPlan, target: str, user_id: int, note: str | None) -> None:
    assert_transition(PLAN_FLOW, plan.status, target)
    old = plan.status
    if target == "issued":
        if not await db.scalar(
            select(func.count())
            .select_from(WorkPackLine)
            .join(WorkPack, WorkPack.id == WorkPackLine.pack_id)
            .where(WorkPack.plan_id == plan.id)
        ):
            raise PlanRuleError("A plan needs at least one work pack with a work anchor before it is issued.")
        plan.issued_at = datetime.now(UTC)
    plan.status = target
    await record_transition(db, "work_plan", plan.id, old, target, user_id, note)
    if target == "issued":
        supervisors = set(
            (await db.execute(select(WorkPack.supervisor_id).where(WorkPack.plan_id == plan.id))).scalars()
        ) | set(
            (
                await db.execute(
                    select(Crew.supervisor_id).join(WorkPack, WorkPack.crew_id == Crew.id).where(WorkPack.plan_id == plan.id)
                )
            ).scalars()
        )
        await notify(
            db,
            [s for s in supervisors if s],
            Category.STATUS,
            f"{plan.code} issued: {plan.title}",
            body=f"{plan.window_start:%d %b} – {plan.window_end:%d %b %Y}",
            link=plan_link(plan),
            entity=("work_plan", plan.id),
            actor_id=user_id,
        )
    await db.flush()
    await publish(
        f"planner.plan.{target}", {"project_id": plan.project_id, "plan_id": plan.id, "code": plan.code, "actor_id": user_id}
    )


# --- packs ---------------------------------------------------------------------------------------------


async def _check_pack_refs(db: AsyncSession, plan: WorkPlan, values: dict[str, Any]) -> None:
    if values.get("crew_id"):
        await get_crew(db, values["crew_id"], plan.project_id)
    start, end = values.get("planned_start"), values.get("planned_end")
    if start and end and end < start:
        raise PlanRuleError("The pack finishes before it starts.")
    if values.get("schedule_activity_id"):
        await _check_activities(db, plan.project_id, [values["schedule_activity_id"]])


async def set_lines(db: AsyncSession, pack: WorkPack, lines: list[dict[str, Any]]) -> None:
    await db.execute(delete(WorkPackLine).where(WorkPackLine.pack_id == pack.id))
    for seq, line in enumerate(lines, start=1):
        anchor = await resolve_anchor(db, pack.project_id, line.pop("node_id", None), line.get("item_id"))
        db.add(WorkPackLine(project_id=pack.project_id, pack_id=pack.id, anchor_id=anchor.id, seq=seq, **line))
    await db.flush()
    await sync_collection(db, await get_plan(db, pack.plan_id))


async def create_pack(db: AsyncSession, plan: WorkPlan, values: dict[str, Any], user_id: int) -> WorkPack:
    if plan.status in ("closed", "cancelled"):
        raise PlanRuleError("Packs can't be added to a closed or cancelled plan.")
    lines = values.pop("lines", [])
    values.pop("plan_id", None)
    await _check_pack_refs(db, plan, values)
    values.setdefault("planned_start", None)
    values["planned_start"] = values["planned_start"] or plan.window_start
    values["planned_end"] = values.get("planned_end") or plan.window_end
    pack = WorkPack(project_id=plan.project_id, plan_id=plan.id, code=await next_reference(db, "JC", plan.project_id), **values)
    db.add(pack)
    await db.flush()
    await set_lines(db, pack, lines)
    await record_transition(db, "work_pack", pack.id, None, pack.status, user_id)
    return pack


async def update_pack(db: AsyncSession, pack: WorkPack, values: dict[str, Any]) -> None:
    plan = await get_plan(db, pack.plan_id)
    await _check_pack_refs(db, plan, {"planned_start": pack.planned_start, "planned_end": pack.planned_end, **values})
    for key, value in values.items():
        setattr(pack, key, value)
    await db.flush()


async def pack_findings(db: AsyncSession, pack: WorkPack) -> list[Finding]:
    anchors = tuple(
        sorted(set((await db.execute(select(WorkPackLine.anchor_id).where(WorkPackLine.pack_id == pack.id))).scalars()))
    )
    ctx = ReadinessContext(
        project_id=pack.project_id,
        pack_id=pack.id,
        anchor_ids=anchors,
        start=pack.planned_start,
        end=pack.planned_end,
        plan_id=pack.plan_id,
        crew_id=pack.crew_id,
        schedule_activity_id=pack.schedule_activity_id,
    )
    return await evaluate(db, ctx)


def readiness_of(findings: list[Finding]) -> str:
    if any(f.severity == Severity.BLOCKER for f in findings):
        return "blocked"
    return "warning" if findings else "ready"


async def read_packs(db: AsyncSession, packs: list[WorkPack], *, detail: bool = False) -> list[dict[str, Any]]:
    ids = [p.id for p in packs]
    crews = (
        {
            c.id: c
            for c in (await db.execute(select(Crew).where(Crew.id.in_({p.crew_id for p in packs if p.crew_id})))).scalars()
        }
        if packs
        else {}
    )
    names = await user_names(db, {p.supervisor_id for p in packs})
    lines: dict[int, list[WorkPackLine]] = defaultdict(list)
    for line in (
        (await db.execute(select(WorkPackLine).where(WorkPackLine.pack_id.in_(ids)).order_by(WorkPackLine.seq))).scalars()
        if ids
        else []
    ):
        lines[line.pack_id].append(line)
    prereqs: dict[int, list[Prerequisite]] = defaultdict(list)
    for pr in (
        (await db.execute(select(Prerequisite).where(Prerequisite.pack_id.in_(ids)).order_by(Prerequisite.id))).scalars()
        if ids
        else []
    ):
        prereqs[pr.pack_id].append(pr)
    nodes = await nodes_by_id(db, {line.anchor_id for ls in lines.values() for line in ls}) if detail else {}
    out = []
    for p in packs:
        findings = await pack_findings(db, p)
        crew = crews.get(p.crew_id or 0)
        read = PackRead.model_validate(p).model_copy(
            update={
                "crew_name": f"{crew.code} {crew.name}" if crew else None,
                "supervisor_name": names.get(p.supervisor_id or 0),
                "planned_hours": sum((line.planned_hours or ZERO for line in lines[p.id]), ZERO),
                "findings": [ReadinessFindingRead(**f.__dict__) for f in findings],
                "readiness": readiness_of(findings),
                "prerequisites": [PrerequisiteRead.model_validate(pr) for pr in prereqs[p.id]],
                "lines": [
                    PackLineRead.model_validate(line).model_copy(
                        update={
                            "anchor_code": nodes[line.anchor_id].display_code or nodes[line.anchor_id].code
                            if line.anchor_id in nodes
                            else None,
                            "anchor_path": nodes[line.anchor_id].display_path if line.anchor_id in nodes else None,
                        }
                    )
                    for line in lines[p.id]
                ]
                if detail
                else [],
            }
        )
        out.append(read.model_dump(mode="json"))
    return out


async def transition_pack(db: AsyncSession, pack: WorkPack, target: str, user_id: int, note: str | None, force: bool) -> None:
    assert_transition(PACK_FLOW, pack.status, target)
    if target == PackStatus.READY:
        blockers = [f for f in await pack_findings(db, pack) if f.severity == Severity.BLOCKER]
        if blockers and not force:
            raise PlanRuleError("Not ready: " + "; ".join(f.message for f in blockers))
        if blockers:
            note = ((note or "") + " [forced past: " + "; ".join(f.message for f in blockers) + "]").strip()
    old = pack.status
    pack.status = target
    await record_transition(db, "work_pack", pack.id, old, target, user_id, note)
    if target == PackStatus.READY:
        crew = await db.get(Crew, pack.crew_id) if pack.crew_id else None
        await notify(
            db,
            [pack.supervisor_id or 0, (crew.supervisor_id or 0) if crew else 0],
            Category.ASSIGNMENT,
            f"{pack.code} is ready to start",
            body=pack.title,
            link=pack_link(pack),
            entity=("work_pack", pack.id),
            actor_id=user_id,
        )
    await db.flush()


# --- built-in readiness providers ----------------------------------------------------------------------


async def _prerequisites(db: AsyncSession, ctx: ReadinessContext) -> list[Finding]:
    rows = (
        await db.execute(
            select(Prerequisite).where(Prerequisite.pack_id == ctx.pack_id, Prerequisite.status == PrerequisiteStatus.PENDING)
        )
    ).scalars()
    today = date.today()
    return [
        Finding(
            "prerequisites",
            p.kind,
            Severity.BLOCKER.value,
            f"{p.kind.replace('_', ' ').capitalize()} not in place: {p.description}"
            + (" (overdue)" if p.required_by and p.required_by < today else ""),
        )
        for p in rows
    ]


async def _constraints(db: AsyncSession, ctx: ReadinessContext) -> list[Finding]:
    where: list[Any] = [PlanConstraint.pack_id == ctx.pack_id]
    if ctx.anchor_ids:
        where.append(PlanConstraint.anchor_id.in_(ctx.anchor_ids))
    if ctx.plan_id:
        where.append(
            (PlanConstraint.plan_id == ctx.plan_id) & PlanConstraint.pack_id.is_(None) & PlanConstraint.anchor_id.is_(None)
        )
    rows = (
        await db.execute(
            select(PlanConstraint).where(
                PlanConstraint.project_id == ctx.project_id, PlanConstraint.status == ConstraintStatus.OPEN, or_(*where)
            )
        )
    ).scalars()
    return [
        Finding("constraints", c.category, Severity.BLOCKER.value, f"{c.code} {c.category}: {c.description[:120]}", c.anchor_id)
        for c in rows
    ]


async def _crew_clash(db: AsyncSession, ctx: ReadinessContext) -> list[Finding]:
    """The pack's crew booked on another plan on a day inside the pack's window."""
    if not ctx.crew_id or not ctx.start or not ctx.end:
        return []
    rows = (
        await db.execute(
            select(DailyAssignment.work_date, WorkPlan.code)
            .join(WorkPlan, WorkPlan.id == DailyAssignment.plan_id)
            .where(
                DailyAssignment.crew_id == ctx.crew_id,
                DailyAssignment.work_date >= ctx.start,
                DailyAssignment.work_date <= ctx.end,
                DailyAssignment.plan_id != ctx.plan_id,
                WorkPlan.status.notin_(("closed", "cancelled")),
            )
            .order_by(DailyAssignment.work_date)
        )
    ).tuples()
    clashes: dict[str, list[date]] = defaultdict(list)
    for day, code in rows:
        if day not in clashes[code]:
            clashes[code].append(day)
    return [
        Finding(
            "crew", "labour", Severity.WARNING.value, f"Crew also booked on {code}: {', '.join(f'{d:%d %b}' for d in days)}"
        )
        for code, days in clashes.items()
    ]


async def _quantities(db: AsyncSession, ctx: ReadinessContext) -> list[Finding]:
    rows = (
        await db.execute(
            select(WorkPackLine.anchor_id, func.sum(WorkPackLine.planned_qty))
            .where(WorkPackLine.pack_id == ctx.pack_id, WorkPackLine.planned_qty.is_not(None))
            .group_by(WorkPackLine.anchor_id)
        )
    ).tuples()
    planned = dict(rows.all())
    nodes = await nodes_by_id(db, set(planned))
    out = []
    for anchor_id, qty in planned.items():
        node = nodes.get(anchor_id)
        if node is None or node.budget_qty is None:
            continue
        remaining = node.budget_qty - (node.earned_qty or ZERO)
        if qty is not None and qty > remaining:
            out.append(
                Finding(
                    "quantities",
                    "scope",
                    Severity.WARNING.value,
                    f"{node.code}: planned {qty:g} {node.uom or ''} but only {remaining:g} remains of the budget".replace(
                        "  ", " "
                    ),
                    anchor_id,
                )
            )
    return out


async def _programme(db: AsyncSession, ctx: ReadinessContext) -> list[Finding]:
    if not ctx.schedule_activity_id:
        return []
    from ..schedule.models import Activity  # noqa: PLC0415 - optional module, only called while it is on

    act = await db.get(Activity, ctx.schedule_activity_id)
    if act is None or act.project_id != ctx.project_id:
        return [Finding("programme", "schedule", Severity.WARNING.value, "The linked programme activity no longer exists.")]
    out = []
    if ctx.start and act.planned_start and ctx.start < act.planned_start:
        out.append(
            Finding(
                "programme",
                "schedule",
                Severity.WARNING.value,
                f"Starts {ctx.start:%d %b}, before programme activity {act.code} ({act.planned_start:%d %b}).",
            )
        )
    if ctx.end and act.planned_finish and ctx.end > act.planned_finish:
        out.append(
            Finding(
                "programme",
                "schedule",
                Severity.WARNING.value,
                f"Finishes {ctx.end:%d %b}, after programme activity {act.code} ({act.planned_finish:%d %b}).",
            )
        )
    return out


register_readiness("planner.prerequisites", "planner", _prerequisites)
register_readiness("planner.constraints", "planner", _constraints)
register_readiness("planner.crew_clash", "planner", _crew_clash)
register_readiness("planner.quantities", "planner", _quantities)
register_readiness("schedule.programme_dates", "schedule", _programme)


# --- constraints ---------------------------------------------------------------------------------------


async def read_constraints(db: AsyncSession, rows: list[PlanConstraint]) -> list[dict[str, Any]]:
    names = await user_names(db, {r.owner_id for r in rows})
    today = date.today()
    return [
        ConstraintRead.model_validate(r)
        .model_copy(
            update={
                "owner_name": names.get(r.owner_id or 0),
                "overdue": bool(r.due_date and r.due_date < today and r.status == ConstraintStatus.OPEN),
            }
        )
        .model_dump(mode="json")
        for r in rows
    ]


async def create_constraint(db: AsyncSession, values: dict[str, Any], user_id: int) -> PlanConstraint:
    project_id = values["project_id"]
    node_id = values.pop("node_id", None)
    anchor_id = (await resolve_anchor(db, project_id, node_id)).id if node_id else None
    if values.get("pack_id"):
        pack = await get_pack(db, values["pack_id"])
        if pack.project_id != project_id:
            raise PackNotFound(str(values["pack_id"]))
        values["plan_id"] = values.get("plan_id") or pack.plan_id
    if values.get("plan_id") and (await get_plan(db, values["plan_id"])).project_id != project_id:
        raise PlanNotFound(str(values["plan_id"]))
    row = PlanConstraint(code=await next_reference(db, "CON", project_id), anchor_id=anchor_id, raised_by_id=user_id, **values)
    db.add(row)
    await db.flush()
    if row.owner_id:
        await notify(
            db,
            [row.owner_id],
            Category.ASSIGNMENT,
            f"Constraint {row.code} is yours to remove",
            body=row.description[:300],
            link=f"/planner?project={project_id}&tab=constraints",
            entity=("plan_constraint", row.id),
            actor_id=user_id,
        )
    return row


async def update_constraint(db: AsyncSession, row: PlanConstraint, values: dict[str, Any], user_id: int) -> None:
    status = values.pop("status", None)
    for key, value in values.items():
        setattr(row, key, value)
    if status and status != row.status:
        await record_transition(db, "plan_constraint", row.id, row.status, status, user_id, values.get("resolution"))
        row.status = status
        row.resolved_at = datetime.now(UTC) if status == ConstraintStatus.RESOLVED else None
    await db.flush()


# --- board and daily plans -----------------------------------------------------------------------------


async def read_assignments(db: AsyncSession, rows: list[DailyAssignment]) -> list[dict[str, Any]]:
    crews = (
        {c.id: c for c in (await db.execute(select(Crew).where(Crew.id.in_({r.crew_id for r in rows})))).scalars()}
        if rows
        else {}
    )
    nodes = await nodes_by_id(db, {r.anchor_id for r in rows})
    packs = (
        dict(
            (
                await db.execute(
                    select(WorkPack.id, WorkPack.code).where(WorkPack.id.in_({r.pack_id for r in rows if r.pack_id}))
                )
            )
            .tuples()
            .all()
        )
        if rows
        else {}
    )
    out = []
    for r in rows:
        crew, node = crews.get(r.crew_id), nodes.get(r.anchor_id)
        out.append(
            AssignmentRead.model_validate(r)
            .model_copy(
                update={
                    "crew_code": crew.code if crew else None,
                    "crew_name": crew.name if crew else None,
                    "anchor_code": (node.display_code or node.code) if node else None,
                    "anchor_path": node.display_path if node else None,
                    "pack_code": packs.get(r.pack_id or 0),
                }
            )
            .model_dump(mode="json")
        )
    return out


async def plan_anchor_packs(db: AsyncSession, plan_id: int) -> dict[int, list[WorkPack]]:
    rows = (
        await db.execute(
            select(WorkPackLine.anchor_id, WorkPack)
            .join(WorkPack, WorkPack.id == WorkPackLine.pack_id)
            .where(WorkPack.plan_id == plan_id)
            .order_by(WorkPack.code, WorkPackLine.seq)
        )
    ).tuples()
    out: dict[int, list[WorkPack]] = defaultdict(list)
    for anchor_id, pack in rows:
        if pack not in out[anchor_id]:
            out[anchor_id].append(pack)
    return out


async def assign(db: AsyncSession, plan: WorkPlan, values: dict[str, Any]) -> tuple[DailyAssignment, list[str]]:
    if plan.status in ("closed", "cancelled"):
        raise PlanRuleError("A closed or cancelled plan can't be assigned.")
    day: date = values["work_date"]
    if not plan.window_start <= day <= plan.window_end:
        raise PlanRuleError(f"{day:%d %b %Y} is outside the plan's window.")
    crew = await get_crew(db, values["crew_id"], plan.project_id)
    anchor_packs = await plan_anchor_packs(db, plan.id)
    if values["anchor_id"] not in anchor_packs:
        raise PlanRuleError("That work anchor isn't in any of this plan's work packs. Add it to a pack first.")
    if values.get("pack_id") is None:
        packs = anchor_packs[values["anchor_id"]]
        values["pack_id"] = next((p.id for p in packs if p.crew_id == crew.id), packs[0].id)
    existing = await db.scalar(
        select(DailyAssignment).where(
            DailyAssignment.crew_id == crew.id,
            DailyAssignment.work_date == day,
            DailyAssignment.anchor_id == values["anchor_id"],
        )
    )
    if existing is not None:
        for key in ("planned_hours", "note", "pack_id"):
            if values.get(key) is not None:
                setattr(existing, key, values[key])
        row = existing
    else:
        row = DailyAssignment(project_id=plan.project_id, **values)
        db.add(row)
    await db.flush()
    return row, await assignment_warnings(db, row, crew)


async def assignment_warnings(db: AsyncSession, row: DailyAssignment, crew: Crew) -> list[str]:
    same_day = list(
        (
            await db.execute(
                select(DailyAssignment).where(
                    DailyAssignment.crew_id == row.crew_id, DailyAssignment.work_date == row.work_date
                )
            )
        ).scalars()
    )
    warnings = []
    other_plans = {a.plan_id for a in same_day if a.plan_id != row.plan_id}
    if other_plans:
        codes = (await db.execute(select(WorkPlan.code).where(WorkPlan.id.in_(other_plans)))).scalars().all()
        warnings.append(f"{crew.code} is also booked on {', '.join(sorted(codes))} that day.")
    hours = sum((a.planned_hours or ZERO for a in same_day), ZERO)
    if hours > crew.shift_hours * max(len(crew.members or []), 1):
        warnings.append(f"{crew.code} has {hours:g} h planned that day, more than its capacity.")
    pack = await db.get(WorkPack, row.pack_id) if row.pack_id else None
    if pack is not None:
        if pack.planned_start and pack.planned_end and not pack.planned_start <= row.work_date <= pack.planned_end:
            warnings.append(f"{row.work_date:%d %b} is outside {pack.code}'s planned dates.")
        state = readiness_of(await pack_findings(db, pack))
        if state == "blocked":
            warnings.append(f"{pack.code} isn't ready: it has open prerequisites or constraints.")
    return warnings


def window_days(plan: WorkPlan) -> list[date]:
    n = min((plan.window_end - plan.window_start).days + 1, MAX_BOARD_DAYS)
    return [plan.window_start + timedelta(days=i) for i in range(n)]


async def board(db: AsyncSession, plan: WorkPlan) -> dict[str, Any]:
    anchor_packs = await plan_anchor_packs(db, plan.id)
    nodes = await nodes_by_id(db, set(anchor_packs))
    totals = {
        a: (q, h)
        for a, q, h in (
            await db.execute(
                select(WorkPackLine.anchor_id, func.sum(WorkPackLine.planned_qty), func.sum(WorkPackLine.planned_hours))
                .join(WorkPack, WorkPack.id == WorkPackLine.pack_id)
                .where(WorkPack.plan_id == plan.id)
                .group_by(WorkPackLine.anchor_id)
            )
        ).tuples()
    }
    uoms = dict(
        (
            await db.execute(
                select(WorkPackLine.anchor_id, func.max(WorkPackLine.uom))
                .join(WorkPack, WorkPack.id == WorkPackLine.pack_id)
                .where(WorkPack.plan_id == plan.id)
                .group_by(WorkPackLine.anchor_id)
            )
        )
        .tuples()
        .all()
    )
    readiness: dict[int, str] = {}
    for packs in anchor_packs.values():
        for p in packs:
            if p.id not in readiness:
                readiness[p.id] = readiness_of(await pack_findings(db, p))
    order = {"blocked": 2, "warning": 1, "ready": 0}
    rows = []
    for anchor_id, packs in sorted(anchor_packs.items(), key=lambda kv: nodes[kv[0]].display_path if kv[0] in nodes else ""):
        node = nodes.get(anchor_id)
        q, h = totals.get(anchor_id, (None, None))
        rows.append(
            {
                "anchor_id": anchor_id,
                "anchor_code": (node.display_code or node.code) if node else str(anchor_id),
                "anchor_path": node.display_path if node else "",
                "pack_ids": [p.id for p in packs],
                "pack_codes": [p.code for p in packs],
                "planned_qty": q,
                "uom": uoms.get(anchor_id) or (node.uom if node else None),
                "planned_hours": h or ZERO,
                "readiness": max((readiness[p.id] for p in packs), key=lambda s: order[s]),
            }
        )
    crews = list(
        (
            await db.execute(select(Crew).where(Crew.project_id == plan.project_id, Crew.active.is_(True)).order_by(Crew.code))
        ).scalars()
    )
    assignments = list(
        (
            await db.execute(
                select(DailyAssignment)
                .where(DailyAssignment.plan_id == plan.id)
                .order_by(DailyAssignment.work_date, DailyAssignment.id)
            )
        ).scalars()
    )
    return {
        "plan": (await read_plans(db, [plan]))[0],
        "days": window_days(plan),
        "rows": rows,
        "crews": await read_crews(db, crews),
        "assignments": await read_assignments(db, assignments),
    }


async def daily_plan(db: AsyncSession, project_id: int, day: date, crew_id: int | None) -> list[DailyAssignment]:
    where: list[Any] = [DailyAssignment.project_id == project_id, DailyAssignment.work_date == day]
    if crew_id:
        where.append(DailyAssignment.crew_id == crew_id)
    return list(
        (
            await db.execute(
                select(DailyAssignment)
                .join(WorkPlan, WorkPlan.id == DailyAssignment.plan_id)
                .where(*where, WorkPlan.status != "cancelled")
                .order_by(DailyAssignment.crew_id, DailyAssignment.id)
            )
        ).scalars()
    )


async def plan_vs_actual(db: AsyncSession, plan: WorkPlan) -> PlanVsActual:
    lines = list(
        (
            await db.execute(
                select(WorkPackLine).join(WorkPack, WorkPack.id == WorkPackLine.pack_id).where(WorkPack.plan_id == plan.id)
            )
        ).scalars()
    )
    planned: dict[int, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    uoms: dict[int, str | None] = {}
    for line in lines:
        planned[line.anchor_id][0] += line.planned_qty or ZERO
        planned[line.anchor_id][1] += line.planned_hours or ZERO
        uoms[line.anchor_id] = uoms.get(line.anchor_id) or line.uom
    nodes = await nodes_by_id(db, set(planned))
    done = await collect_actuals(db, plan.project_id, sorted(planned), plan.window_start, plan.window_end)
    days = dict(
        (
            await db.execute(
                select(DailyAssignment.anchor_id, func.count(func.distinct(DailyAssignment.work_date)))
                .where(DailyAssignment.plan_id == plan.id)
                .group_by(DailyAssignment.anchor_id)
            )
        )
        .tuples()
        .all()
    )
    rows = []
    for anchor_id, (pq, ph) in sorted(planned.items(), key=lambda kv: nodes[kv[0]].display_path if kv[0] in nodes else ""):
        node = nodes.get(anchor_id)
        act = done.get(anchor_id)
        aq, ah = (act.qty, act.hours) if act else (ZERO, ZERO)
        rows.append(
            PlanVsActualRow(
                anchor_id=anchor_id,
                anchor_code=(node.display_code or node.code) if node else str(anchor_id),
                anchor_path=node.display_path if node else "",
                uom=uoms.get(anchor_id) or (node.uom if node else None),
                budget_qty=node.budget_qty if node else None,
                planned_qty=pq,
                actual_qty=aq,
                earned_qty=node.earned_qty if node else None,
                planned_hours=ph,
                actual_hours=ah,
                assigned_days=days.get(anchor_id, 0),
                hours_variance=ph - ah,
                percent_qty=round(float(aq / pq) * 100, 1) if pq else None,
            )
        )
    return PlanVsActual(
        plan_id=plan.id,
        rows=rows,
        planned_hours=sum((r.planned_hours for r in rows), ZERO),
        actual_hours=sum((r.actual_hours for r in rows), ZERO),
        planned_qty=sum((r.planned_qty for r in rows), ZERO),
        actual_qty=sum((r.actual_qty for r in rows), ZERO),
    )


# --- issue a work pack ---------------------------------------------------------------------------------


def _num(value: Decimal | None) -> str:
    return "" if value is None else f"{value.normalize():f}"


async def pack_pdf(db: AsyncSession, pack: WorkPack, user_id: int) -> bytes:
    plan = await get_plan(db, pack.plan_id)
    read = (await read_packs(db, [pack], detail=True))[0]
    crew = await db.get(Crew, pack.crew_id) if pack.crew_id else None
    daily = list(
        (
            await db.execute(
                select(DailyAssignment).where(DailyAssignment.pack_id == pack.id).order_by(DailyAssignment.work_date)
            )
        ).scalars()
    )
    doc = Document(title=f"Work pack {pack.code}", subtitle=f"{pack.title} · {plan.code} {plan.title}", footer=pack.code)
    doc.fields(
        [
            ("Plan", f"{plan.code} {plan.title} ({plan.kind.replace('_', ' ')})"),
            ("Window", f"{plan.window_start:%d %b %Y} – {plan.window_end:%d %b %Y}"),
            ("Pack dates", f"{pack.planned_start or ''} – {pack.planned_end or ''}"),
            ("Crew", read["crew_name"] or "—"),
            ("Supervisor", read["supervisor_name"] or "—"),
            ("Access", pack.access or "—"),
            ("Status", pack.status.replace("_", " ")),
            ("Readiness", read["readiness"]),
        ]
    )
    doc.heading("Scope")
    doc.table(
        ["#", "Work anchor", "Activity", "Description", "Qty", "UoM", "Hours"],
        [
            [
                line["seq"],
                line["anchor_path"] or line["anchor_code"],
                line["activity_code"] or "",
                line["description"] or "",
                _num(Decimal(str(line["planned_qty"])) if line["planned_qty"] is not None else None),
                line["uom"] or "",
                _num(Decimal(str(line["planned_hours"])) if line["planned_hours"] is not None else None),
            ]
            for line in read["lines"]
        ],
        widths=[0.05, 0.3, 0.1, 0.3, 0.08, 0.07, 0.1],
        numeric={4, 6},
    )
    if read["prerequisites"]:
        doc.heading("Prerequisites")
        doc.table(
            ["Kind", "Description", "Required by", "Reference", "Status"],
            [
                [p["kind"], p["description"], p["required_by"] or "", p["reference"] or "", p["status"].replace("_", " ")]
                for p in read["prerequisites"]
            ],
            widths=[0.12, 0.43, 0.15, 0.15, 0.15],
        )
    if read["findings"]:
        doc.heading("Readiness warnings")
        doc.table(
            ["Severity", "Source", "Finding"],
            [[f["severity"], f["source"], f["message"]] for f in read["findings"]],
            widths=[0.12, 0.15, 0.73],
        )
    if daily:
        doc.heading("Daily plan")
        reads = await read_assignments(db, daily)
        doc.table(
            ["Date", "Crew", "Work anchor", "Hours", "Note"],
            [[a["work_date"], a["crew_code"], a["anchor_code"], a["planned_hours"] or "", a["note"] or ""] for a in reads],
            widths=[0.13, 0.12, 0.35, 0.1, 0.3],
            numeric={3},
        )
    if crew and crew.members:
        doc.heading("Crew")
        doc.table(["Name", "Trade"], [[m.get("name", ""), m.get("trade") or ""] for m in crew.members], widths=[0.6, 0.4])
    if pack.notes:
        doc.heading("Notes")
        doc.paragraph(pack.notes)
    doc.heading("Issue and sign-off")
    doc.table(["Role", "Name", "Signature", "Date"], [["Issued by", "", "", ""], ["Supervisor", "", "", ""]])
    pack.issued_at = datetime.now(UTC)
    await record_transition(db, "work_pack", pack.id, pack.status, pack.status, user_id, "Work pack PDF issued")
    return render_pdf(doc)
