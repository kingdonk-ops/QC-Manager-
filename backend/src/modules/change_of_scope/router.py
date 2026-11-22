"""Mounted at /api/v1/change-of-scope."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.exceptions import PermissionDeniedError
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.models import Project
from ..projects.service import readable_project
from . import service
from .constants import CardStatus, ChangeType
from .models import ChangeCard
from .permissions import ChangeOfScopePermissionName as P
from .schemas import CardCreate, CardRead, CardStatusChange, CardSummary, CardUpdate

router = APIRouter(tags=["Change of Scope"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


class MissingPermission(PermissionDeniedError):
    public_detail = "You don't have permission for that status change."


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _card(db: AsyncSession, card_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[ChangeCard, Project]:
    card = await service.get_card(db, card_id)
    project = await readable_project(db, card.project_id, user["id"], held)
    return card, project


def _where(
    project_id: int,
    status: str | None,
    change_type: ChangeType | None,
    node_id: int | None,
    change_order_id: int | None,
    search: str | None,
) -> list[Any]:
    where: list[Any] = [ChangeCard.project_id == project_id]
    if status == "waiting":
        where.append(ChangeCard.status.in_(("submitted", "acknowledged")))
    elif status:
        where.append(ChangeCard.status == status)
    if change_type:
        where.append(ChangeCard.change_type == change_type.value)
    if node_id:
        where.append((ChangeCard.node_id == node_id) | (ChangeCard.work_anchor_id == node_id))
    if change_order_id:
        where.append(ChangeCard.change_order_id == change_order_id)
    if search:
        like = f"%{search.lower()}%"
        where.append(
            func.lower(ChangeCard.code + " " + ChangeCard.title + " " + func.coalesce(ChangeCard.client_reference, "")).like(
                like
            )
        )
    return where


StatusFilter = Annotated[
    str | None, Query(pattern=r"^(waiting|draft|submitted|acknowledged|approved|rejected|converted|expired|withdrawn)$")
]


@router.get(
    "/cards/",
    response_model=PaginatedListResponse[CardRead],
    summary="The Change-of-Scope Register",
    description="`status=waiting` lists cards waiting for the client (submitted or acknowledged). "
    "`change_order_id` finds the card a change order came from.",
    dependencies=perm(P.READ),
)
async def list_cards(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    status: StatusFilter = None,
    change_type: ChangeType | None = None,
    node_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    change_order_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = _where(project_id, status, change_type, node_id, change_order_id, search)
    total = await db.scalar(select(func.count()).select_from(ChangeCard).where(*where))
    rows = list(
        (
            await db.execute(
                select(ChangeCard)
                .where(*where)
                .order_by(ChangeCard.id.desc())
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await service.read(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get("/summary", response_model=CardSummary, summary="Change-of-Scope Totals", dependencies=perm(P.READ))
async def summary(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.summary(db, project_id)


@router.get("/cards/export", summary="Export the Register", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv"] = "xlsx",
    status: StatusFilter = None,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    rows = list(
        (
            await db.execute(
                select(ChangeCard).where(*_where(project_id, status, None, None, None, None)).order_by(ChangeCard.id)
            )
        ).scalars()
    )
    body, media, ext = write_table(service.EXPORT_COLUMNS, await service.read(db, rows), format, title="Change of scope")
    name = f"change-of-scope-{project.code}.{ext}"
    return Response(body, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.post("/cards/", response_model=CardRead, status_code=201, summary="Raise a Change Card", dependencies=perm(P.CREATE))
async def create(values: CardCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, values.project_id, user["id"], held)
    card = await service.create(db, project, values.model_dump(mode="python"), user["id"])
    return (await service.read(db, [card]))[0]


@router.get("/cards/{card_id}", response_model=CardRead, summary="A Change Card", dependencies=perm(P.READ))
async def get(card_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    card, _ = await _card(db, card_id, user, held)
    return (await service.read(db, [card]))[0]


@router.patch("/cards/{card_id}", response_model=CardRead, summary="Edit a Draft Card", dependencies=perm(P.UPDATE))
async def update(
    card_id: Id, values: CardUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    card, _ = await _card(db, card_id, user, held)
    await service.update(db, card, values.model_dump(mode="python", exclude_unset=True))
    return (await service.read(db, [card]))[0]


@router.delete("/cards/{card_id}", status_code=204, summary="Delete a Draft Card", dependencies=perm(P.DELETE))
async def delete(card_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> None:
    card, _ = await _card(db, card_id, user, held)
    await service.delete(db, card)


@router.patch(
    "/cards/{card_id}/status",
    response_model=CardRead,
    summary="Move a Card Through Its Workflow",
    description="Submitting starts the 14-day expiry. `acknowledged` needs change_of_scope.respond; "
    "`approved`/`rejected` need change_of_scope.approve; the rest need change_of_scope.submit.",
    dependencies=perm(P.READ),
)
async def move(
    card_id: Id, values: CardStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    card, _ = await _card(db, card_id, user, held)
    if values.status in (CardStatus.EXPIRED, CardStatus.CONVERTED):
        raise MissingPermission("expired and converted are set by the system")
    if service.required_permission(values.status) not in held:
        raise MissingPermission(values.status)
    await service.transition(db, card, values.status, user["id"], values.note, values.approved_amount)
    return (await service.read(db, [card]))[0]


@router.post(
    "/cards/{card_id}/convert",
    response_model=CardRead,
    summary="Convert an Approved Card to a Change Order",
    description="Creates an approved change order with the card's lines (scaled to the approved amount) and links "
    "the two. Needs the Change Orders module.",
    dependencies=perm(P.APPROVE),
)
async def convert(card_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    card, project = await _card(db, card_id, user, held)
    await service.convert(db, card, project, user["id"])
    return (await service.read(db, [card]))[0]


@router.get("/cards/{card_id}/history", summary="A Card's Status History", dependencies=perm(P.READ))
async def history(card_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    card, _ = await _card(db, card_id, user, held)
    return await history_of(db, service.ENTITY, card.id)
