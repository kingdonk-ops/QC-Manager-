"""Mounted at /api/v1/planner."""

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..asset_tree.models import AssetCollection
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import PackStatus, PlanStatus, PrerequisiteStatus
from .models import Crew, DailyAssignment, PlanConstraint, Prerequisite, WorkPack, WorkPlan
from .permissions import PlannerPermissionName as P
from .readiness import readiness_providers
from .schemas import (
    AssignmentIn,
    AssignmentRead,
    ConstraintIn,
    ConstraintRead,
    ConstraintUpdate,
    CrewIn,
    CrewRead,
    CrewUpdate,
    PackIn,
    PackLinesIn,
    PackRead,
    PackUpdate,
    PlanBoard,
    PlanIn,
    PlannerTransition,
    PlanRead,
    PlanUpdate,
    PlanVsActual,
    PrerequisiteIn,
    PrerequisiteRead,
    PrerequisiteUpdate,
)

router = APIRouter(tags=["Planner"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _plan(db: Any, plan_id: int, user: dict, held: frozenset[str]) -> WorkPlan:
    plan = await service.get_plan(db, plan_id)
    await readable_project(db, plan.project_id, user["id"], held)
    return plan


async def _pack(db: Any, pack_id: int, user: dict, held: frozenset[str]) -> WorkPack:
    pack = await service.get_pack(db, pack_id)
    await readable_project(db, pack.project_id, user["id"], held)
    return pack


# --- crews ---------------------------------------------------------------------------------------------


@router.get("/crews/", response_model=PaginatedListResponse[CrewRead], summary="List Crews", dependencies=perm(P.READ))
async def list_crews(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    active: bool | None = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Crew.project_id == project_id] + ([Crew.active.is_(active)] if active is not None else [])
    total = await db.scalar(select(func.count()).select_from(Crew).where(*where))
    rows = (
        await db.execute(
            select(Crew).where(*where).order_by(Crew.code).offset(compute_offset(page, items_per_page)).limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_crews(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/crews/", response_model=CrewRead, status_code=201, summary="Add a Crew", dependencies=perm(P.CREATE))
async def create_crew(values: CrewIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    if await db.scalar(select(Crew.id).where(Crew.project_id == values.project_id, Crew.code == values.code)):
        raise service.PlanRuleError(f"Crew {values.code} already exists.")
    crew = Crew(**values.model_dump(mode="python", exclude={"members"}), members=[m.model_dump() for m in values.members])
    db.add(crew)
    await db.commit()
    return (await service.read_crews(db, [crew]))[0]


@router.patch("/crews/{crew_id}", response_model=CrewRead, summary="Change a Crew", dependencies=perm(P.UPDATE))
async def update_crew(
    crew_id: Id, values: CrewUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    crew = await service.get_crew(db, crew_id)
    await readable_project(db, crew.project_id, user["id"], held)
    changes = values.model_dump(exclude_unset=True)
    if "members" in changes and values.members is not None:
        changes["members"] = [m.model_dump() for m in values.members]
    for key, value in changes.items():
        setattr(crew, key, value)
    await db.commit()
    return (await service.read_crews(db, [crew]))[0]


@router.delete("/crews/{crew_id}", summary="Remove a Crew", dependencies=perm(P.DELETE))
async def delete_crew(crew_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    crew = await service.get_crew(db, crew_id)
    await readable_project(db, crew.project_id, user["id"], held)
    await db.delete(crew)
    await db.commit()
    return {"message": "Crew removed"}


# --- plans ---------------------------------------------------------------------------------------------


@router.get(
    "/plans/",
    response_model=PaginatedListResponse[PlanRead],
    summary="List Work Plans",
    dependencies=perm(P.READ),
)
async def list_plans(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    status: PlanStatus | None = None,
    covering: Annotated[date | None, Query(description="Plans whose window includes this day")] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [WorkPlan.project_id == project_id]
    if status:
        where.append(WorkPlan.status == status.value)
    if covering:
        where += [WorkPlan.window_start <= covering, WorkPlan.window_end >= covering]
    total = await db.scalar(select(func.count()).select_from(WorkPlan).where(*where))
    rows = (
        await db.execute(
            select(WorkPlan)
            .where(*where)
            .order_by(WorkPlan.window_start.desc(), WorkPlan.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_plans(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/plans/",
    response_model=PlanRead,
    status_code=201,
    summary="Create a Work Plan",
    description="Also creates the plan's asset-tree collection (kind `work_plan`), kept in step with its packs' work anchors.",
    dependencies=perm(P.CREATE),
)
async def create_plan(values: PlanIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    plan = await service.create_plan(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return (await service.read_plans(db, [plan]))[0]


@router.get("/plans/{plan_id}", response_model=PlanRead, summary="Get a Work Plan", dependencies=perm(P.READ))
async def get_plan(plan_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    plan = await _plan(db, plan_id, user, held)
    return (await service.read_plans(db, [plan]))[0]


@router.patch("/plans/{plan_id}", response_model=PlanRead, summary="Change a Work Plan", dependencies=perm(P.UPDATE))
async def update_plan(
    plan_id: Id, values: PlanUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    plan = await _plan(db, plan_id, user, held)
    await service.update_plan(db, plan, values.model_dump(mode="python", exclude_unset=True))
    await db.commit()
    return (await service.read_plans(db, [plan]))[0]


@router.post(
    "/plans/{plan_id}/transition",
    response_model=PlanRead,
    summary="Issue, Start, Close or Cancel a Plan",
    description="draft → issued → in_execution → closed; issued → draft to revise; any open plan → cancelled.",
    dependencies=perm(P.TRANSITION),
)
async def transition_plan(
    plan_id: Id, values: PlannerTransition, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    plan = await _plan(db, plan_id, user, held)
    await service.transition_plan(db, plan, values.status, user["id"], values.note)
    await db.commit()
    return (await service.read_plans(db, [plan]))[0]


@router.get("/plans/{plan_id}/history", summary="A Plan's Status History", dependencies=perm(P.READ))
async def plan_history(plan_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    plan = await _plan(db, plan_id, user, held)
    return await history_of(db, "work_plan", plan.id)


@router.delete("/plans/{plan_id}", summary="Delete a Draft or Cancelled Plan", dependencies=perm(P.DELETE))
async def delete_plan(plan_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    plan = await _plan(db, plan_id, user, held)
    if plan.status not in ("draft", "cancelled"):
        raise service.PlanRuleError("Only a draft or cancelled plan can be deleted.")
    collection = await db.get(AssetCollection, plan.collection_id) if plan.collection_id else None
    await db.delete(plan)
    if collection is not None:
        await db.delete(collection)
    await db.commit()
    return {"message": "Plan deleted"}


@router.get(
    "/plans/{plan_id}/board",
    response_model=PlanBoard,
    summary="The Look-Ahead PlanBoard",
    description="Work anchors (rows) × days of the window (columns), with crew assignments and readiness per anchor.",
    dependencies=perm(P.READ),
)
async def plan_board(plan_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    plan = await _plan(db, plan_id, user, held)
    return await service.board(db, plan)


@router.get(
    "/plans/{plan_id}/plan-vs-actual",
    response_model=PlanVsActual,
    summary="Plan Against Actual per Work Anchor",
    description="Planned quantities and hours from the plan's packs; actuals from providers such as the daily workface log.",
    dependencies=perm(P.READ),
)
async def plan_vs_actual(plan_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    plan = await _plan(db, plan_id, user, held)
    return await service.plan_vs_actual(db, plan)


# --- packs ---------------------------------------------------------------------------------------------


@router.get(
    "/packs/",
    response_model=PaginatedListResponse[PackRead],
    summary="List Work Packs",
    description="With readiness findings; `detail=true` adds lines.",
    dependencies=perm(P.READ),
)
async def list_packs(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    plan_id: Annotated[int | None, Query(ge=1)] = None,
    crew_id: Annotated[int | None, Query(ge=1)] = None,
    status: PackStatus | None = None,
    detail: bool = False,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [WorkPack.project_id == project_id]
    if plan_id:
        where.append(WorkPack.plan_id == plan_id)
    if crew_id:
        where.append(WorkPack.crew_id == crew_id)
    if status:
        where.append(WorkPack.status == status.value)
    total = await db.scalar(select(func.count()).select_from(WorkPack).where(*where))
    rows = (
        await db.execute(
            select(WorkPack)
            .where(*where)
            .order_by(WorkPack.planned_start, WorkPack.code)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_packs(db, list(rows), detail=detail), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/packs/",
    response_model=PackRead,
    status_code=201,
    summary="Create a Work Pack",
    description="Lines take any node or item; each resolves to the work anchor on its path (422 `NoWorkAnchor` otherwise).",
    dependencies=perm(P.CREATE),
)
async def create_pack(values: PackIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    plan = await _plan(db, values.plan_id, user, held)
    data = values.model_dump(mode="python")
    data["lines"] = [line.model_dump(mode="python") for line in values.lines]
    pack = await service.create_pack(db, plan, data, user["id"])
    await db.commit()
    return (await service.read_packs(db, [pack], detail=True))[0]


@router.get("/packs/{pack_id}", response_model=PackRead, summary="Get a Work Pack", dependencies=perm(P.READ))
async def get_pack(pack_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    pack = await _pack(db, pack_id, user, held)
    return (await service.read_packs(db, [pack], detail=True))[0]


@router.patch("/packs/{pack_id}", response_model=PackRead, summary="Change a Work Pack", dependencies=perm(P.UPDATE))
async def update_pack(
    pack_id: Id, values: PackUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    pack = await _pack(db, pack_id, user, held)
    await service.update_pack(db, pack, values.model_dump(mode="python", exclude_unset=True))
    await db.commit()
    return (await service.read_packs(db, [pack], detail=True))[0]


@router.put("/packs/{pack_id}/lines", response_model=PackRead, summary="Set a Pack's Scope Lines", dependencies=perm(P.UPDATE))
async def set_lines(
    pack_id: Id, values: PackLinesIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    pack = await _pack(db, pack_id, user, held)
    await service.set_lines(db, pack, [line.model_dump(mode="python") for line in values.lines])
    await db.commit()
    return (await service.read_packs(db, [pack], detail=True))[0]


@router.post(
    "/packs/{pack_id}/transition",
    response_model=PackRead,
    summary="Move a Work Pack",
    description="planned → ready → in_progress → done, or deferred. `ready` is refused while blockers remain, unless `force`.",
    dependencies=perm(P.TRANSITION),
)
async def transition_pack(
    pack_id: Id, values: PlannerTransition, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    pack = await _pack(db, pack_id, user, held)
    await service.transition_pack(db, pack, values.status, user["id"], values.note, values.force)
    await db.commit()
    return (await service.read_packs(db, [pack], detail=True))[0]


@router.get("/packs/{pack_id}/history", summary="A Pack's Status History", dependencies=perm(P.READ))
async def pack_history(pack_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    pack = await _pack(db, pack_id, user, held)
    return await history_of(db, "work_pack", pack.id)


@router.get("/packs/{pack_id}/pdf", summary="Issue the Work Pack (PDF)", dependencies=perm(P.EXPORT))
async def pack_pdf(pack_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    pack = await _pack(db, pack_id, user, held)
    pdf = await service.pack_pdf(db, pack, user["id"])
    await db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{pack.code}.pdf"'})


@router.delete("/packs/{pack_id}", summary="Delete a Work Pack", dependencies=perm(P.DELETE))
async def delete_pack(pack_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    pack = await _pack(db, pack_id, user, held)
    if pack.status not in ("planned", "deferred"):
        raise service.PlanRuleError("Only a planned or deferred pack can be deleted.")
    plan = await service.get_plan(db, pack.plan_id)
    await db.delete(pack)
    await db.flush()
    await service.sync_collection(db, plan)
    await db.commit()
    return {"message": "Pack deleted"}


# --- prerequisites -------------------------------------------------------------------------------------


@router.post(
    "/packs/{pack_id}/prerequisites",
    response_model=PrerequisiteRead,
    status_code=201,
    summary="Add a Prerequisite",
    dependencies=perm(P.UPDATE),
)
async def add_prerequisite(
    pack_id: Id, values: PrerequisiteIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    pack = await _pack(db, pack_id, user, held)
    row = Prerequisite(project_id=pack.project_id, pack_id=pack.id, **values.model_dump(mode="python"))
    if row.status == PrerequisiteStatus.CLEARED:
        row.cleared_by_id = user["id"]
    db.add(row)
    await db.commit()
    return row


async def _prerequisite(db: Any, prereq_id: int, user: dict, held: frozenset[str]) -> Prerequisite:
    row: Prerequisite | None = await db.get(Prerequisite, prereq_id)
    if row is None:
        raise service.PrerequisiteNotFound(str(prereq_id))
    await readable_project(db, row.project_id, user["id"], held)
    return row


@router.patch(
    "/prerequisites/{prereq_id}",
    response_model=PrerequisiteRead,
    summary="Clear or Change a Prerequisite",
    dependencies=perm(P.UPDATE),
)
async def update_prerequisite(
    prereq_id: Id, values: PrerequisiteUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _prerequisite(db, prereq_id, user, held)
    changes = values.model_dump(mode="python", exclude_unset=True)
    if "status" in changes and changes["status"] != row.status:
        cleared = changes["status"] == PrerequisiteStatus.CLEARED
        row.cleared_at = datetime.now(UTC) if cleared else None
        row.cleared_by_id = user["id"] if cleared else None
    for key, value in changes.items():
        setattr(row, key, value)
    await db.commit()
    return row


@router.delete("/prerequisites/{prereq_id}", summary="Remove a Prerequisite", dependencies=perm(P.UPDATE))
async def delete_prerequisite(
    prereq_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    row = await _prerequisite(db, prereq_id, user, held)
    await db.delete(row)
    await db.commit()
    return {"message": "Prerequisite removed"}


@router.get(
    "/readiness-providers",
    summary="Registered Readiness Providers",
    description="Readiness checks other modules plugged in (key, owning module).",
    dependencies=perm(P.READ),
)
async def providers(_: CurrentUserDep) -> list[dict[str, str]]:
    return [{"key": k, "module": m} for k, m in readiness_providers()]


# --- constraints ---------------------------------------------------------------------------------------


@router.get(
    "/constraints/",
    response_model=PaginatedListResponse[ConstraintRead],
    summary="The Constraint Log",
    dependencies=perm(P.READ),
)
async def list_constraints(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    status: Annotated[str | None, Query(pattern=r"^(open|resolved)$")] = None,
    plan_id: Annotated[int | None, Query(ge=1)] = None,
    pack_id: Annotated[int | None, Query(ge=1)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [PlanConstraint.project_id == project_id]
    if status:
        where.append(PlanConstraint.status == status)
    if plan_id:
        where.append(PlanConstraint.plan_id == plan_id)
    if pack_id:
        where.append(PlanConstraint.pack_id == pack_id)
    total = await db.scalar(select(func.count()).select_from(PlanConstraint).where(*where))
    rows = (
        await db.execute(
            select(PlanConstraint)
            .where(*where)
            .order_by(PlanConstraint.status, PlanConstraint.due_date.is_(None), PlanConstraint.due_date, PlanConstraint.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_constraints(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/constraints/", response_model=ConstraintRead, status_code=201, summary="Log a Constraint", dependencies=perm(P.CREATE)
)
async def create_constraint(
    values: ConstraintIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    row = await service.create_constraint(db, values.model_dump(mode="python"), user["id"])
    await db.commit()
    return (await service.read_constraints(db, [row]))[0]


@router.patch(
    "/constraints/{constraint_id}",
    response_model=ConstraintRead,
    summary="Change or Resolve a Constraint",
    dependencies=perm(P.UPDATE),
)
async def update_constraint(
    constraint_id: Id, values: ConstraintUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await service.get_constraint(db, constraint_id)
    await readable_project(db, row.project_id, user["id"], held)
    await service.update_constraint(db, row, values.model_dump(mode="python", exclude_unset=True), user["id"])
    await db.commit()
    return (await service.read_constraints(db, [row]))[0]


# --- assignments and daily plans -----------------------------------------------------------------------


@router.post(
    "/assignments",
    response_model=AssignmentRead,
    summary="Put a Crew on a Work Anchor for a Day",
    description="One board cell. Repeating the same crew/anchor/day updates it. Conflicts come back as `warnings`.",
    dependencies=perm(P.ASSIGN),
)
async def assign(values: AssignmentIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    plan = await _plan(db, values.plan_id, user, held)
    row, warnings = await service.assign(db, plan, values.model_dump(mode="python"))
    await db.commit()
    read = (await service.read_assignments(db, [row]))[0]
    return {**read, "warnings": warnings}


@router.delete("/assignments/{assignment_id}", summary="Take a Crew off a Day", dependencies=perm(P.ASSIGN))
async def unassign(assignment_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    row = await db.get(DailyAssignment, assignment_id)
    if row is None:
        raise service.AssignmentNotFound(str(assignment_id))
    await readable_project(db, row.project_id, user["id"], held)
    await db.delete(row)
    await db.commit()
    return {"message": "Assignment removed"}


@router.get(
    "/daily-plan",
    response_model=list[AssignmentRead],
    summary="What Each Crew Works on That Day",
    dependencies=perm(P.READ),
)
async def daily_plan(
    project_id: ProjectQ,
    work_date: date,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    crew_id: Annotated[int | None, Query(ge=1)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.read_assignments(db, await service.daily_plan(db, project_id, work_date, crew_id))
