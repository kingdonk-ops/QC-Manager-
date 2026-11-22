"""Mounted at /api/v1/numbering."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...infrastructure.audit_ledger import changes, record_audit
from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import NotFoundException, UnprocessableEntityException
from ...infrastructure.records.models import AllocatedNumber, NumberingScheme
from ...infrastructure.records.schemes import AUTO_TOKENS, CODE_TOKENS, NumberingError, allocate, check_scheme, parse_pattern
from ...infrastructure.records.schemes import preview as preview_number
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from .permissions import NumberingPermissionName as P
from .schemas import (
    AllocateIn,
    AllocationRead,
    PreviewIn,
    PreviewRead,
    SchemeIn,
    SchemeRead,
    SchemeUpdate,
    TokenRead,
    VoidIn,
)

router = APIRouter(tags=["Numbering schemes"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _snapshot(s: NumberingScheme) -> dict[str, Any]:
    return {
        "pattern": s.pattern,
        "counter_scope": list(s.counter_scope),
        "code_lists": dict(s.code_lists),
        "start_value": s.start_value,
        "active": s.active,
        "name": s.name,
    }


async def _scheme(db: Any, scheme_id: int, user: dict[str, Any], held: frozenset[str]) -> NumberingScheme:
    scheme: NumberingScheme | None = await db.get(NumberingScheme, scheme_id)
    if scheme is None:
        raise NotFoundException("No such numbering scheme")
    await readable_project(db, scheme.project_id, user["id"], held)
    return scheme


async def _read(db: Any, schemes: list[NumberingScheme]) -> list[dict[str, Any]]:
    ids = [s.id for s in schemes]
    counts = (
        dict(
            (
                await db.execute(
                    select(AllocatedNumber.scheme_id, func.count())
                    .where(AllocatedNumber.scheme_id.in_(ids))
                    .group_by(AllocatedNumber.scheme_id)
                )
            )
            .tuples()
            .all()
        )
        if ids
        else {}
    )
    return [
        SchemeRead.model_validate(s).model_copy(update={"allocated": counts.get(s.id, 0)}).model_dump(mode="json")
        for s in schemes
    ]


def _check(pattern: str, counter_scope: list[str], code_lists: dict[str, Any]) -> None:
    problems = check_scheme(pattern, counter_scope, code_lists)
    if problems:
        raise UnprocessableEntityException("; ".join(problems))


@router.get("/tokens", response_model=list[TokenRead], summary="Tokens a Pattern May Use")
async def tokens(_: CurrentUserDep) -> list[TokenRead]:
    return [TokenRead(token=k, kind="auto", description=v) for k, v in AUTO_TOKENS.items()] + [
        TokenRead(token=k, kind="code", description=v) for k, v in CODE_TOKENS.items()
    ]


@router.post(
    "/preview",
    response_model=PreviewRead,
    summary="Preview a Pattern",
    description="The next number a pattern would give, without allocating it. Missing code values print as the token name.",
    dependencies=perm(P.READ),
)
async def preview(values: PreviewIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> PreviewRead:
    await readable_project(db, values.project_id, user["id"], held)
    result = await preview_number(
        db,
        values.project_id,
        values.pattern,
        counter_scope=values.counter_scope,
        code_lists={k: [c.model_dump() for c in v] for k, v in values.code_lists.items()},
        start_value=values.start_value,
        values=values.values,
        scheme_id=values.scheme_id,
        year=datetime.now(UTC).year,
    )
    return PreviewRead(
        number=result.number,
        sequence=result.sequence,
        scope_key=result.scope_key,
        errors=result.errors,
        tokens=[p.token for p in parse_pattern(values.pattern).parts if p.token],
    )


@router.get(
    "/schemes/",
    response_model=PaginatedListResponse[SchemeRead],
    summary="A Project's Numbering Schemes",
    dependencies=perm(P.READ),
)
async def list_schemes(
    project_id: Annotated[int, Query(ge=1)],
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = NumberingScheme.project_id == project_id
    total = await db.scalar(select(func.count()).select_from(NumberingScheme).where(where))
    rows = (
        await db.execute(
            select(NumberingScheme)
            .where(where)
            .order_by(NumberingScheme.record_kind)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return paginated_response(
        crud_data={"data": await _read(db, list(rows)), "total_count": total or 0}, page=page, items_per_page=items_per_page
    )


@router.post("/schemes/", response_model=SchemeRead, status_code=201, summary="Create a Scheme", dependencies=perm(P.MANAGE))
async def create_scheme(values: SchemeIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    data = values.model_dump(mode="json")
    _check(data["pattern"], data["counter_scope"], data["code_lists"])
    scheme = NumberingScheme(**data, updated_by_id=user["id"])
    db.add(scheme)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise UnprocessableEntityException(f"The project already has a scheme for '{values.record_kind}'.") from exc
    await record_audit(
        db,
        "numbering.scheme.created",
        "numbering_scheme",
        scheme.id,
        actor_id=user["id"],
        project_id=scheme.project_id,
        summary=f"{scheme.record_kind}: {scheme.pattern}",
        after=_snapshot(scheme),
    )
    await db.commit()
    return (await _read(db, [scheme]))[0]


@router.get("/schemes/{scheme_id}", response_model=SchemeRead, summary="Get a Scheme", dependencies=perm(P.READ))
async def get_scheme(scheme_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await _read(db, [await _scheme(db, scheme_id, user, held)]))[0]


@router.patch(
    "/schemes/{scheme_id}",
    response_model=SchemeRead,
    summary="Change a Scheme",
    description="Only new numbers follow the change; numbers already allocated never change.",
    dependencies=perm(P.MANAGE),
)
async def update_scheme(
    scheme_id: Id, values: SchemeUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    scheme = await _scheme(db, scheme_id, user, held)
    old = _snapshot(scheme)
    data = values.model_dump(mode="json", exclude_unset=True)
    merged = {**old, **{k: v for k, v in data.items() if v is not None or k == "name"}}
    _check(merged["pattern"], merged["counter_scope"], merged["code_lists"])
    for key, value in merged.items():
        setattr(scheme, key, value)
    scheme.updated_by_id = user["id"]
    before, after = changes(old, _snapshot(scheme))
    if after:
        await record_audit(
            db,
            "numbering.scheme.changed",
            "numbering_scheme",
            scheme.id,
            actor_id=user["id"],
            project_id=scheme.project_id,
            summary=f"{scheme.record_kind}: {scheme.pattern}",
            before=before,
            after=after,
        )
    await db.commit()
    return (await _read(db, [scheme]))[0]


@router.delete(
    "/schemes/{scheme_id}",
    summary="Delete an Unused Scheme",
    description="A scheme that has allocated numbers can't be deleted; switch it off (`active: false`) instead.",
    dependencies=perm(P.MANAGE),
)
async def delete_scheme(
    scheme_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    scheme = await _scheme(db, scheme_id, user, held)
    if await db.scalar(select(AllocatedNumber.id).where(AllocatedNumber.scheme_id == scheme.id).limit(1)):
        raise UnprocessableEntityException("Numbers were allocated from this scheme: switch it off instead.")
    await record_audit(
        db,
        "numbering.scheme.deleted",
        "numbering_scheme",
        scheme.id,
        actor_id=user["id"],
        project_id=scheme.project_id,
        before=_snapshot(scheme),
    )
    await db.delete(scheme)
    await db.commit()
    return {"message": "Scheme deleted"}


@router.post(
    "/schemes/{scheme_id}/allocate",
    response_model=AllocationRead,
    status_code=201,
    summary="Allocate the Next Number",
    description="Reserve a number by hand (for a record made outside the app). Allocated numbers are never reused.",
    dependencies=perm(P.ASSIGN),
)
async def allocate_number(
    scheme_id: Id, values: AllocateIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    scheme = await _scheme(db, scheme_id, user, held)
    if not scheme.active:
        raise UnprocessableEntityException("The scheme is switched off.")
    entity = (values.entity_type, values.entity_id) if values.entity_type and values.entity_id else None
    try:
        row = await allocate(db, scheme, values.values, entity=entity, user_id=user["id"], year=datetime.now(UTC).year)
    except NumberingError as exc:
        raise UnprocessableEntityException("; ".join(exc.problems)) from exc
    await db.commit()
    return row


@router.get(
    "/allocations/",
    response_model=PaginatedListResponse[AllocationRead],
    summary="The Number Register",
    dependencies=perm(P.READ),
)
async def list_allocations(
    project_id: Annotated[int, Query(ge=1)],
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    record_kind: Annotated[str | None, Query(max_length=40)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AllocatedNumber.project_id == project_id]
    if record_kind:
        where.append(AllocatedNumber.record_kind == record_kind)
    if search:
        where.append(func.lower(AllocatedNumber.number).like(f"%{search.lower()}%"))
    total = await db.scalar(select(func.count()).select_from(AllocatedNumber).where(*where))
    rows = (
        await db.execute(
            select(AllocatedNumber)
            .where(*where)
            .order_by(AllocatedNumber.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = [AllocationRead.model_validate(r).model_dump(mode="json") for r in rows]
    return paginated_response(crud_data={"data": data, "total_count": total or 0}, page=page, items_per_page=items_per_page)


@router.post(
    "/allocations/{allocation_id}/void",
    response_model=AllocationRead,
    summary="Void a Number",
    description="The number stays in the register, marked void, and is never handed out again.",
    dependencies=perm(P.ASSIGN),
)
async def void_allocation(
    allocation_id: Id, values: VoidIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await db.get(AllocatedNumber, allocation_id)
    if row is None:
        raise NotFoundException("No such number")
    await readable_project(db, row.project_id, user["id"], held)
    row.voided, row.void_reason = True, values.reason
    await record_audit(
        db,
        "numbering.number.voided",
        "numbering_allocation",
        row.id,
        actor_id=user["id"],
        project_id=row.project_id,
        summary=f"{row.number}: {values.reason}",
    )
    await db.commit()
    return row
