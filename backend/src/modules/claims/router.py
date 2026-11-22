"""Mounted at /api/v1/claims."""

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
from .models import Claim, RateItem
from .permissions import ClaimPermissionName as P
from .schemas import (
    ClaimCreate,
    ClaimDetail,
    ClaimRead,
    ClaimStatus,
    ClaimStatusChange,
    ClaimUpdate,
    LineRead,
    LineUpdate,
    RateItemCreate,
    RateItemRead,
    RateItemUpdate,
    SeedResult,
)

router = APIRouter(tags=["Progress Claims"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]


class CertifierOnly(PermissionDeniedError):
    public_detail = "Recording certification or payment needs claims.approve."


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _claim(db: AsyncSession, claim_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[Claim, Project]:
    claim = await service.get_claim(db, claim_id)
    return claim, await readable_project(db, claim.project_id, user["id"], held)


async def _item(db: AsyncSession, item_id: int, user: dict[str, Any], held: frozenset[str]) -> RateItem:
    item = await service.get_rate_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    return item


# --- schedule of rates ---------------------------------------------------------------------------


@router.get(
    "/rate-items/",
    response_model=PaginatedListResponse[RateItemRead],
    summary="Schedule of Rates",
    dependencies=perm(P.READ),
)
async def list_rate_items(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    total = await db.scalar(select(func.count()).select_from(RateItem).where(RateItem.project_id == project_id))
    rows = list(
        (
            await db.execute(
                select(RateItem)
                .where(RateItem.project_id == project_id)
                .order_by(RateItem.sort_order, RateItem.code)
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await service.read_rate_items(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/rate-items/", response_model=RateItemRead, status_code=201, summary="Add a Rate Item", dependencies=perm(P.UPDATE)
)
async def create_rate_item(
    values: RateItemCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    item = await service.create_rate_item(db, values.model_dump())
    return (await service.read_rate_items(db, [item]))[0]


@router.post(
    "/rate-items/from-tree",
    response_model=SeedResult,
    summary="Add Rate Items for Every Progress Unit",
    description="One item per progress-unit node not priced yet, with its budget quantity and unit; rates start at 0.",
    dependencies=perm(P.UPDATE),
)
async def seed(db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, project_id: ProjectQuery) -> SeedResult:
    await readable_project(db, project_id, user["id"], held)
    return SeedResult(created=await service.seed_from_tree(db, project_id))


@router.patch("/rate-items/{item_id}", response_model=RateItemRead, summary="Change a Rate Item", dependencies=perm(P.UPDATE))
async def update_rate_item(
    item_id: Id, values: RateItemUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await _item(db, item_id, user, held)
    await service.update_rate_item(db, item, values.model_dump(exclude_unset=True))
    return (await service.read_rate_items(db, [item]))[0]


@router.delete("/rate-items/{item_id}", status_code=204, summary="Delete a Rate Item", dependencies=perm(P.UPDATE))
async def delete_rate_item(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> None:
    item = await _item(db, item_id, user, held)
    await db.delete(item)
    await db.commit()


# --- claims --------------------------------------------------------------------------------------


@router.get("/", response_model=PaginatedListResponse[ClaimRead], summary="Progress Claims", dependencies=perm(P.READ))
async def list_claims(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    status: ClaimStatus | None = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    project = await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [Claim.project_id == project_id]
    if status:
        where.append(Claim.status == status.value)
    total = await db.scalar(select(func.count()).select_from(Claim).where(*where))
    rows = (
        await db.execute(
            select(Claim)
            .where(*where)
            .order_by(Claim.period_end.desc(), Claim.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [await service.read_claim(db, c, project.currency) for c in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get("/export", summary="Export the Claims Register", dependencies=perm(P.EXPORT))
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    format: Literal["xlsx", "csv"] = "xlsx",
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    claims = (
        await db.execute(select(Claim).where(Claim.project_id == project_id).order_by(Claim.period_end, Claim.id))
    ).scalars()
    rows = []
    for c in claims:
        r = await service.read_claim(db, c, project.currency)
        rows.append({**r, **r["totals"]})
    body, media, ext = write_table(service.EXPORT_COLUMNS, rows, format, title="Progress claims")
    name = f"claims-{project.code}.{ext}"
    return Response(body, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.post(
    "/",
    response_model=ClaimDetail,
    status_code=201,
    summary="Start a Progress Claim",
    description="Fills the lines from the schedule of rates (verified quantities only) and approved variations.",
    dependencies=perm(P.CREATE),
)
async def create_claim(values: ClaimCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, values.project_id, user["id"], held)
    claim = await service.create_claim(db, project, values.model_dump(), user["id"])
    return await service.read_claim(db, claim, project.currency, with_lines=True)


@router.get("/{claim_id}", response_model=ClaimDetail, summary="A Claim with Its Lines", dependencies=perm(P.READ))
async def get_claim(claim_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    claim, project = await _claim(db, claim_id, user, held)
    return await service.read_claim(db, claim, project.currency, with_lines=True)


@router.patch("/{claim_id}", response_model=ClaimDetail, summary="Change a Draft Claim", dependencies=perm(P.UPDATE))
async def update_claim(
    claim_id: Id, values: ClaimUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    claim, project = await _claim(db, claim_id, user, held)
    await service.update_claim(db, claim, values.model_dump(exclude_unset=True))
    return await service.read_claim(db, claim, project.currency, with_lines=True)


@router.delete("/{claim_id}", status_code=204, summary="Delete a Draft Claim", dependencies=perm(P.DELETE))
async def delete_claim(claim_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> None:
    claim, _ = await _claim(db, claim_id, user, held)
    await service.delete_claim(db, claim)


@router.post(
    "/{claim_id}/refresh",
    response_model=ClaimDetail,
    summary="Refresh a Draft from Verified Progress",
    dependencies=perm(P.UPDATE),
)
async def refresh(claim_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    claim, project = await _claim(db, claim_id, user, held)
    await service.refresh(db, claim)
    await db.commit()
    return await service.read_claim(db, claim, project.currency, with_lines=True)


@router.patch(
    "/{claim_id}/lines/{line_id}",
    response_model=LineRead,
    summary="Claim Less Than Verified",
    description="Set a line's quantity to date. A work line can't exceed its verified quantity.",
    dependencies=perm(P.UPDATE),
)
async def update_line(
    claim_id: Id, line_id: Id, values: LineUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    claim, _ = await _claim(db, claim_id, user, held)
    line = await service.get_line(db, claim, line_id)
    return service.read_line(await service.set_to_date(db, claim, line, values.to_date_qty))


@router.patch(
    "/{claim_id}/status",
    response_model=ClaimDetail,
    summary="Submit, Certify or Record Payment",
    description="`submitted` freezes the figures (needs claims.submit); `certified` needs the certified amount and "
    "`paid` the payment (both need claims.approve).",
    dependencies=perm(P.READ),
)
async def move(
    claim_id: Id, values: ClaimStatusChange, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    claim, project = await _claim(db, claim_id, user, held)
    needed = P.APPROVE if values.status in (ClaimStatus.CERTIFIED, ClaimStatus.PAID) else P.SUBMIT
    if needed.value not in held:
        raise CertifierOnly(values.status)
    await service.transition(db, claim, values.status, user["id"], values.model_dump())
    return await service.read_claim(db, claim, project.currency, with_lines=True)


@router.get("/{claim_id}/pdf", summary="The Claim as PDF", dependencies=perm(P.EXPORT))
async def claim_pdf(claim_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Response:
    claim, project = await _claim(db, claim_id, user, held)
    body = await service.pdf(db, claim, project)
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{claim.code}.pdf"'})


@router.get("/{claim_id}/history", summary="A Claim's Status History", dependencies=perm(P.READ))
async def history(claim_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    claim, _ = await _claim(db, claim_id, user, held)
    return await history_of(db, service.ENTITY, claim.id)
