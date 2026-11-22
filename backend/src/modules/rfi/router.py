"""Mounted at /api/v1/rfis."""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from ..tasks.permissions import TaskPermissionName
from ..tasks.service import create_task
from ..user.models import User
from . import service
from .constants import ENTITY, RfiStatus
from .models import Rfi, RfiSettings
from .permissions import RfiPermissionName as P
from .schemas import (
    CreatedTask,
    RfiCreate,
    RfiDetail,
    RfiRead,
    RfiRespond,
    RfiSettingsRead,
    RfiSettingsSet,
    RfiStatusChange,
    RfiTaskCreate,
    RfiUpdate,
    UserOption,
)

router = APIRouter(tags=["RFIs"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
BallFilter = Annotated[str | None, Query(pattern=r"^(me|contractor|designer|client|consultant|subcontractor)$")]
Discipline = Annotated[str | None, Query(max_length=60)]
Search = Annotated[str | None, Query(max_length=100)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _filters(
    project_id: int,
    user_id: int,
    status: RfiStatus | None,
    ball_in_court: str | None,
    overdue: bool,
    discipline: str | None,
    search: str | None,
) -> list[Any]:
    where: list[Any] = [Rfi.project_id == project_id]
    if status:
        where.append(Rfi.status == status.value)
    if ball_in_court == "me":
        where.append(Rfi.bic_user_id == user_id)
    elif ball_in_court:
        where.append(Rfi.ball_in_court == ball_in_court)
    if overdue:
        where += service.overdue_filter(date.today())
    if discipline:
        where.append(func.lower(Rfi.discipline) == discipline.lower())
    if search:
        where.append(service.search_filter(search))
    return where


@router.get(
    "/",
    response_model=PaginatedListResponse[RfiRead],
    summary="List RFIs",
    description="A project's RFI register. `ball_in_court` takes a party, or `me` for RFIs waiting on you.",
    dependencies=perm(P.READ),
)
async def list_rfis(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: RfiStatus | None = None,
    ball_in_court: BallFilter = None,
    overdue: bool = False,
    discipline: Discipline = None,
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = _filters(project_id, user["id"], status, ball_in_court, overdue, discipline, search)
    total = await db.scalar(select(func.count()).select_from(Rfi).where(*where))
    rows = (
        await db.execute(
            select(Rfi).where(*where).order_by(Rfi.id.desc()).offset(compute_offset(page, items_per_page)).limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_rfis(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=RfiRead, status_code=201, summary="Raise an RFI", dependencies=perm(P.CREATE))
async def create(values: RfiCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    rfi = await service.create_rfi(db, values.model_dump(), user)
    return (await service.read_rfis(db, [rfi]))[0]


EXPORT_COLUMNS = [
    ("code", "No."),
    ("subject", "Subject"),
    ("discipline", "Discipline"),
    ("location", "Location"),
    ("priority", "Priority"),
    ("status", "Status"),
    ("raised_by_name", "Raised by"),
    ("ball_in_court", "Ball in court"),
    ("bic_name", "Action by"),
    ("opened_on", "Opened"),
    ("due_date", "Due"),
    ("days_open", "Days open"),
    ("overdue", "Overdue"),
    ("impact", "Impact"),
    ("cost_impact_amount", "Cost impact"),
    ("schedule_impact_days", "Days impact"),
]


@router.get(
    "/export",
    summary="Export the RFI Register",
    description="The register, with the same filters as the listing, as Excel, CSV or PDF.",
    dependencies=perm(P.EXPORT),
)
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv", "pdf"] = "xlsx",
    status: RfiStatus | None = None,
    ball_in_court: BallFilter = None,
    overdue: bool = False,
    discipline: Discipline = None,
    search: Search = None,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    where = _filters(project_id, user["id"], status, ball_in_court, overdue, discipline, search)
    rfis = list((await db.execute(select(Rfi).where(*where).order_by(Rfi.id))).scalars())
    rows = []
    for r in await service.read_rfis(db, rfis):
        impacts = [k for k in ("cost", "schedule", "scope") if r[f"{k}_impact"]]
        rows.append(
            {
                **r,
                "bic_name": r["bic_user_name"] or r["bic_contact_name"],
                "overdue": "Yes" if r["overdue"] else "",
                "impact": ", ".join(impacts),
                "status": r["status"].replace("_", " "),
            }
        )
    filename = f"{project.code}-rfis"
    if format == "pdf":
        doc = Document(title="RFI Register", subtitle=f"{project.name} · {project.code}", landscape=True)
        headers = ["No.", "Subject", "Status", "Ball in court", "Action by", "Opened", "Due", "Days", "Impact"]
        doc.table(
            headers,
            [
                [
                    r["code"],
                    r["subject"],
                    r["status"] + (" (overdue)" if r["overdue"] else ""),
                    r["ball_in_court"] or "",
                    r["bic_name"] or "",
                    r["opened_on"] or "",
                    r["due_date"] or "",
                    r["days_open"] if r["days_open"] is not None else "",
                    r["impact"],
                ]
                for r in rows
            ],
            widths=[0.08, 0.3, 0.1, 0.1, 0.14, 0.08, 0.08, 0.05, 0.07],
            numeric={7},
        )
        return Response(
            render_pdf(doc),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    body, media_type, ext = write_table(EXPORT_COLUMNS, rows, format, title="RFIs")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}.{ext}"'})


@router.get("/users", response_model=list[UserOption], summary="People an RFI Can Be Addressed To", dependencies=perm(P.READ))
async def users(db: AsyncSessionDep, _: CurrentUserDep) -> list[UserOption]:
    rows = await db.execute(select(User.id, User.name).where(User.is_deleted.is_(False)).order_by(User.name).limit(500))
    return [UserOption(id=i, name=n) for i, n in rows.all()]


@router.get(
    "/settings/{project_id}", response_model=RfiSettingsRead, summary="A Project's RFI Settings", dependencies=perm(P.READ)
)
async def get_settings(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return RfiSettingsRead(project_id=project_id, default_due_days=await service.due_days(db, project_id))


@router.put(
    "/settings/{project_id}",
    response_model=RfiSettingsRead,
    summary="Set a Project's RFI Settings",
    description="`default_due_days`: how long the addressee has to answer a new RFI.",
    dependencies=perm(P.UPDATE),
)
async def set_settings(
    project_id: Id, values: RfiSettingsSet, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    settings = await db.get(RfiSettings, project_id)
    if settings is None:
        db.add(RfiSettings(project_id=project_id, default_due_days=values.default_due_days))
    else:
        settings.default_due_days = values.default_due_days
    await db.commit()
    return RfiSettingsRead(project_id=project_id, default_due_days=values.default_due_days)


async def _readable(db: AsyncSessionDep, rfi_id: int, user: dict[str, Any], held: frozenset[str]) -> Rfi:
    rfi = await service.get_rfi(db, rfi_id)
    await readable_project(db, rfi.project_id, user["id"], held)
    return rfi


async def _detail(db: AsyncSessionDep, rfi: Rfi) -> dict[str, Any]:
    return {**(await service.read_rfis(db, [rfi]))[0], "responses": await service.responses_of(db, rfi.id)}


@router.get("/{rfi_id}", response_model=RfiDetail, summary="Get an RFI with Its Responses", dependencies=perm(P.READ))
async def get(rfi_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _detail(db, await _readable(db, rfi_id, user, held))


@router.patch("/{rfi_id}", response_model=RfiDetail, summary="Update an RFI", dependencies=perm(P.UPDATE))
async def update(rfi_id: Id, values: RfiUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    rfi = await _readable(db, rfi_id, user, held)
    await service.update_rfi(db, rfi, values.model_dump(exclude_unset=True))
    return await _detail(db, rfi)


@router.delete("/{rfi_id}", summary="Delete an RFI", dependencies=perm(P.DELETE))
async def delete(rfi_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    rfi = await _readable(db, rfi_id, user, held)
    await db.delete(rfi)
    await db.commit()
    return {"message": "RFI deleted"}


@router.patch(
    "/{rfi_id}/status",
    response_model=RfiDetail,
    summary="Change an RFI's Status or Ball in Court",
    description="Draft → open → answered → closed; answered → open for a follow-up; anything → void.",
    dependencies=perm(P.TRANSITION),
)
async def change_status(
    rfi_id: Id, values: RfiStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    rfi = await _readable(db, rfi_id, user, held)
    await service.change_status(db, rfi, values.model_dump(exclude_unset=True), user)
    return await _detail(db, rfi)


@router.post(
    "/{rfi_id}/respond",
    response_model=RfiDetail,
    summary="Respond to an RFI",
    description="Adds to the thread. An answer moves an open RFI to answered and hands the ball back to the raiser.",
    dependencies=perm(P.RESPOND),
)
async def respond(
    rfi_id: Id, values: RfiRespond, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    rfi = await _readable(db, rfi_id, user, held)
    await service.respond(db, rfi, values.body, values.is_answer, values.attachment_ids, user)
    return await _detail(db, rfi)


@router.get("/{rfi_id}/history", summary="An RFI's Status History", dependencies=perm(P.READ))
async def history(rfi_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    rfi = await _readable(db, rfi_id, user, held)
    rows = await history_of(db, ENTITY, rfi.id)
    names = await service.user_names(db, {r["changed_by_id"] for r in rows if r["changed_by_id"]})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"])} for r in rows]


@router.post(
    "/{rfi_id}/task",
    response_model=CreatedTask,
    status_code=201,
    summary="Create a Task from an RFI",
    dependencies=[require_permissions(P.UPDATE.value, TaskPermissionName.CREATE.value)],
)
async def task_from_rfi(
    rfi_id: Id, values: RfiTaskCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> CreatedTask:
    rfi = await _readable(db, rfi_id, user, held)
    task = await create_task(
        db,
        project_id=rfi.project_id,
        title=values.title or f"{rfi.code}: {rfi.subject}"[:300],
        created_by_id=user["id"],
        entity=(ENTITY, rfi.id),
        assignee_id=values.assignee_id or rfi.bic_user_id,
        due_date=values.due_date or rfi.due_date,
        description=rfi.question,
    )
    return CreatedTask(id=task.id, code=task.code, title=task.title)
