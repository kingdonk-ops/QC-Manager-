"""Mounted at /api/v1/scaffolds. Every route reads the scaffold's project through ``readable_project`` first."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..asset_tree import service as tree
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import STANDING, ScaffoldStatus, Tag
from .models import Scaffold, ScaffoldInspection, ScaffoldModification
from .permissions import ScaffoldPermissionName as P
from .schemas import (
    HireSummary,
    InspectionRequest,
    ModificationCreate,
    ModificationDecision,
    ModificationRead,
    Readiness,
    ReadinessBlocker,
    ScaffoldCreate,
    ScaffoldInspectionCreate,
    ScaffoldInspectionRead,
    ScaffoldRead,
    ScaffoldTransition,
    ScaffoldUpdate,
    StatusChangeRead,
    TagBoard,
    WeatherEvent,
)

router = APIRouter(tags=["Scaffolds"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _readable(db: Any, scaffold_id: int, user: dict[str, Any], held: frozenset[str]) -> Scaffold:
    s = await service.get_scaffold(db, scaffold_id)
    await readable_project(db, s.project_id, user["id"], held)
    return s


async def _one(db: Any, s: Scaffold) -> dict[str, Any]:
    return (await service.read_scaffolds(db, [s]))[0]


def _filters(
    project_id: int, status: str | None, search: str | None, node_ids: list[int] | None, active_only: bool
) -> list[Any]:
    where: list[Any] = [Scaffold.project_id == project_id]
    if status:
        where.append(Scaffold.status == status)
    if active_only:
        where.append(Scaffold.status.not_in(["rejected", "cancelled", "dismantled"]))
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Scaffold.code).like(like),
                func.lower(func.coalesce(Scaffold.tag_no, "")).like(like),
                func.lower(func.coalesce(Scaffold.location_text, "")).like(like),
            )
        )
    if node_ids is not None:
        where.append(Scaffold.node_id.in_(node_ids))
    return where


@router.get(
    "/",
    response_model=PaginatedListResponse[ScaffoldRead],
    summary="The Scaffold Register",
    description="Filter by status, effective `tag` (an overdue inspection reads red), area `node_id` (with its subtree), "
    "`active_only`, or search code / tag no. / location.",
    dependencies=perm(P.READ),
)
async def list_scaffolds(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: ScaffoldStatus | None = None,
    tag: Tag | None = None,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    active_only: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    nodes = None
    if node_id is not None:
        await tree.get_node(db, node_id, project_id)
        nodes = await tree.subtree_ids(db, node_id, with_lineage=False)
    where = _filters(project_id, status.value if status else None, search, nodes, active_only)
    if tag is not None:
        rows = list((await db.execute(select(Scaffold).where(*where).order_by(Scaffold.code))).scalars())
        read = [r for r in await service.read_scaffolds(db, rows) if r["effective_tag"] == tag.value]
        start = compute_offset(page, items_per_page)
        data = {"data": read[start : start + items_per_page], "total_count": len(read)}
    else:
        total = await db.scalar(select(func.count()).select_from(Scaffold).where(*where))
        rows = list(
            (
                await db.execute(
                    select(Scaffold)
                    .where(*where)
                    .order_by(Scaffold.code)
                    .offset(compute_offset(page, items_per_page))
                    .limit(items_per_page)
                )
            ).scalars()
        )
        data = {"data": await service.read_scaffolds(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=ScaffoldRead, status_code=201, summary="Request a Scaffold", dependencies=perm(P.CREATE))
async def create(values: ScaffoldCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    s = await service.create_scaffold(db, values.model_dump(), user)
    return await _one(db, s)


@router.get(
    "/tag-board",
    response_model=TagBoard,
    summary="Standing Scaffolds by Tag",
    description="Every standing scaffold in a column by its effective tag (overdue inspections are red).",
    dependencies=perm(P.READ),
)
async def tag_board(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> Any:
    await readable_project(db, project_id, user["id"], held)
    rows = list(
        (
            await db.execute(
                select(Scaffold)
                .where(Scaffold.project_id == project_id, Scaffold.status.in_([s.value for s in STANDING]))
                .order_by(Scaffold.code)
            )
        ).scalars()
    )
    read = await service.read_scaffolds(db, rows)
    return {t.value: [r for r in read if r["effective_tag"] == t.value] for t in Tag}


@router.get(
    "/hire",
    response_model=HireSummary,
    summary="Scaffold Hire: Days × Rate",
    description="Days on hire per scaffold within the period (erection and dismantle days count), times its daily rate. "
    "A mirror for reconciling the scaffold contractor's hire invoice.",
    dependencies=perm(P.READ),
)
async def hire(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    start: date | None = None,
    end: date | None = None,
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    end = end or date.today()
    lines = await service.hire_lines(db, project_id, start, end)
    return HireSummary(
        project_id=project_id,
        currency=project.currency,
        period_start=start,
        period_end=end,
        lines=lines,
        total_days=sum(line["days"] for line in lines),
        total_cost=sum((line["cost"] or Decimal(0) for line in lines), Decimal(0)),
    )


@router.get(
    "/readiness",
    response_model=Readiness,
    summary="Is the Scaffold Access for a Node Ready on a Day",
    description="What the planner asks: every scaffold serving the node (or beneath it) erected, tagged green or yellow, "
    "and inspected within its interval on that day.",
    dependencies=perm(P.READ),
)
async def readiness(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    node_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    on_date: date | None = None,
) -> Any:
    node = await tree.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    day = on_date or date.today()
    ready, rows, blockers = await service.scaffold_readiness(db, node_id, day)
    return Readiness(
        node_id=node_id,
        on_date=day,
        ready=ready,
        scaffolds=len(rows),
        blockers=[ReadinessBlocker(**b.__dict__) for b in blockers],
    )


@router.post(
    "/weather-events",
    response_model=list[ScaffoldRead],
    summary="Record a Weather Event",
    description="High wind, storm or heavy rain: every standing scaffold in the area is due for inspection now (its tag "
    "reads red until re-inspected) and its custodian gets an inspection task.",
    dependencies=perm(P.UPDATE),
)
async def weather(values: WeatherEvent, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    if values.node_id is not None:
        await tree.get_node(db, values.node_id, values.project_id)
    rows = await service.weather_event(db, values.project_id, values.node_id, values.description, user)
    return await service.read_scaffolds(db, rows)


EXPORT_COLUMNS = [
    ("code", "Scaffold"),
    ("tag_no", "Tag no."),
    ("status", "Status"),
    ("effective_tag", "Tag"),
    ("node_path", "Location"),
    ("location_text", "Location detail"),
    ("scaffold_type", "Type"),
    ("duty_class", "Duty"),
    ("required_by", "Required by"),
    ("erected_on", "Erected"),
    ("last_inspected_at", "Last inspected"),
    ("next_inspection_due", "Next inspection due"),
    ("dismantled_on", "Dismantled"),
    ("days_erected", "Days erected"),
    ("hire_rate", "Rate / day"),
    ("hire_cost", "Hire cost"),
]


@router.get("/export", summary="Export the Scaffold Register", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    rows = list((await db.execute(select(Scaffold).where(Scaffold.project_id == project_id).order_by(Scaffold.code))).scalars())
    body, media_type, ext = write_table(
        EXPORT_COLUMNS, await service.read_scaffolds(db, rows), format, title="Scaffold register"
    )
    name = f"scaffold-register-{project.code}.{ext}"
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{scaffold_id}", response_model=ScaffoldRead, summary="Get a Scaffold", dependencies=perm(P.READ))
async def get(scaffold_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _one(db, await _readable(db, scaffold_id, user, held))


@router.patch("/{scaffold_id}", response_model=ScaffoldRead, summary="Edit a Scaffold", dependencies=perm(P.UPDATE))
async def update(
    scaffold_id: Id, values: ScaffoldUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    await service.update_scaffold(db, s, changes)
    return await _one(db, s)


@router.delete("/{scaffold_id}", summary="Delete a Scaffold", dependencies=perm(P.DELETE))
async def delete(scaffold_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    s = await _readable(db, scaffold_id, user, held)
    await db.delete(s)
    await db.commit()
    return {"message": "Scaffold deleted"}


@router.post(
    "/{scaffold_id}/transition",
    response_model=ScaffoldRead,
    summary="Move a Scaffold Through Its Lifecycle",
    description="approve/reject and the go-ahead to dismantle need `scaffolds.approve`; a dismantle request "
    "`scaffolds.create`; erecting, erected, modifying and dismantled `scaffolds.transition`. The requester may cancel. "
    "`in_use` comes only from a passing inspection.",
    dependencies=perm(P.READ),
)
async def transition(
    scaffold_id: Id, values: ScaffoldTransition, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    await service.transition(db, s, values.status.value, user, held, values.on, values.note)
    return await _one(db, s)


@router.get(
    "/{scaffold_id}/history", response_model=list[StatusChangeRead], summary="Status History", dependencies=perm(P.READ)
)
async def history(scaffold_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    return await history_of(db, service.ENTITY, s.id)


@router.get(
    "/{scaffold_id}/inspections",
    response_model=list[ScaffoldInspectionRead],
    summary="Inspections and Tags",
    dependencies=perm(P.READ),
)
async def inspections(scaffold_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    rows = (
        await db.execute(
            select(ScaffoldInspection)
            .where(ScaffoldInspection.scaffold_id == s.id)
            .order_by(ScaffoldInspection.inspected_at.desc(), ScaffoldInspection.id.desc())
        )
    ).scalars()
    return await service.read_inspections(db, list(rows))


@router.post(
    "/{scaffold_id}/inspections",
    response_model=ScaffoldInspectionRead,
    status_code=201,
    summary="Inspect and Tag",
    description="Green or yellow hands an erected scaffold over (`in_use`) and sets the next inspection due "
    "`inspection_interval_days` later; red takes it out of use.",
    dependencies=perm(P.INSPECT),
)
async def add_inspection(
    scaffold_id: Id, values: ScaffoldInspectionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    row = await service.inspect(db, s, values.model_dump(), user)
    return (await service.read_inspections(db, [row]))[0]


@router.post(
    "/{scaffold_id}/inspection-requests",
    summary="Request an Inspection",
    description="Creates an inspection task for the scaffold's custodian, due today.",
    dependencies=perm(P.CREATE),
)
async def request_inspection(
    scaffold_id: Id, values: InspectionRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, int]:
    s = await _readable(db, scaffold_id, user, held)
    return {"task_id": await service.request_inspection(db, s, values.reason.value, values.note, user)}


@router.get(
    "/{scaffold_id}/modifications",
    response_model=list[ModificationRead],
    summary="Modification Requests",
    dependencies=perm(P.READ),
)
async def modifications(scaffold_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    rows = await db.execute(
        select(ScaffoldModification).where(ScaffoldModification.scaffold_id == s.id).order_by(ScaffoldModification.id)
    )
    return list(rows.scalars())


@router.post(
    "/{scaffold_id}/modifications",
    response_model=ModificationRead,
    status_code=201,
    summary="Request a Modification",
    dependencies=perm(P.CREATE),
)
async def add_modification(
    scaffold_id: Id, values: ModificationCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    return await service.request_modification(db, s, values.model_dump(), user)


@router.post(
    "/{scaffold_id}/modifications/{modification_id}/decision",
    response_model=ModificationRead,
    summary="Approve, Reject or Complete a Modification",
    description="Approval (`scaffolds.approve`) takes the scaffold out of use (`modifying`, red tag); completion "
    "(`scaffolds.transition`) returns it to `erected`, awaiting a fresh handover inspection.",
    dependencies=perm(P.READ),
)
async def decide_modification(
    scaffold_id: Id,
    modification_id: Id,
    values: ModificationDecision,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    s = await _readable(db, scaffold_id, user, held)
    m = await db.get(ScaffoldModification, modification_id)
    if m is None or m.scaffold_id != s.id:
        raise service.ScaffoldNotFound(str(modification_id))
    await service.decide_modification(db, s, m, values.status.value, values.note, user, held)
    return m
