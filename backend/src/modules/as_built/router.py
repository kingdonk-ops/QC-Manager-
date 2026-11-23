"""Mounted at /api/v1/as-built: list, create, read, edit, delete, survey, verify and sign."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..inspections.constants import ToleranceResult
from ..projects.service import readable_project
from . import service
from .constants import AsBuiltStatus
from .models import AsBuiltRecord
from .permissions import AsBuiltPermissionName as P
from .schemas import AsBuiltCreate, AsBuiltRead, AsBuiltSign, AsBuiltSurvey, AsBuiltUpdate, AsBuiltVerify

router = APIRouter(tags=["As-Built Records"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]
CREATE = [require_permissions(P.CREATE.value)]
UPDATE = [require_permissions(P.UPDATE.value)]
DELETE = [require_permissions(P.DELETE.value)]
REVIEW = [require_permissions(P.REVIEW.value)]
APPROVE = [require_permissions(P.APPROVE.value)]


async def _readable(
    db: Any, record_id: int, user: dict[str, Any], held: frozenset[str], *, lock: bool = False
) -> AsBuiltRecord:
    """The record once the caller may see its project. ``lock`` re-reads it under a row lock, so two concurrent steps on
    one record (verify twice, verify against sign) run in turn and the second sees the new status."""
    record = await service.get_record(db, record_id)
    await readable_project(db, record.project_id, user["id"], held)
    if lock:
        await db.refresh(record, with_for_update=True)
    return record


@router.get(
    "/",
    response_model=PaginatedListResponse[AsBuiltRead],
    summary="List As-Built Records",
    description="A project's as-built records, newest first. Filter by status and by tolerance result, for example to "
    "find surveyed records that are out of tolerance and not yet verified.",
    dependencies=READ,
)
async def list_records(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    status: AsBuiltStatus | None = None,
    tolerance_result: ToleranceResult | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AsBuiltRecord.project_id == project_id]
    if status:
        where.append(AsBuiltRecord.status == status.value)
    if tolerance_result:
        where.append(AsBuiltRecord.tolerance_result == tolerance_result.value)
    total = await db.scalar(select(func.count()).select_from(AsBuiltRecord).where(*where))
    rows = (
        await db.execute(
            select(AsBuiltRecord)
            .where(*where)
            .order_by(AsBuiltRecord.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [AsBuiltRead.model_validate(r).model_dump(mode="json") for r in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=AsBuiltRead,
    status_code=201,
    summary="Create an As-Built Record",
    description="Starts as a draft with the next project number. A criterion, node or item of another project answers "
    "not-found.",
    dependencies=CREATE,
)
async def create_record(values: AsBuiltCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    return await service.create_record(db, values.model_dump(), user["id"])


@router.get("/{record_id}", response_model=AsBuiltRead, summary="Get an As-Built Record", dependencies=READ)
async def get_record(record_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _readable(db, record_id, user, held)


@router.patch(
    "/{record_id}",
    response_model=AsBuiltRead,
    summary="Edit an As-Built Record",
    description="An edit never sets surveyed, verified or recorded: use the survey, verify and sign actions (conflict). "
    "It moves a draft or surveyed record to void and a verified one to superseded. Once surveyed, the measured value and "
    "criterion change only by a new survey (conflict). A verified or superseded record is not rewritten (conflict) and "
    "a recorded or void record cannot be edited.",
    dependencies=UPDATE,
)
async def update_record(
    record_id: Id, values: AsBuiltUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    record = await _readable(db, record_id, user, held, lock=True)
    return await service.update_record(db, record, values.model_dump(exclude_unset=True), user["id"])


@router.delete(
    "/{record_id}",
    summary="Delete an As-Built Record",
    description="Draft, surveyed and void records only; verified and later records are kept as evidence.",
    dependencies=DELETE,
)
async def delete_record(
    record_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await service.delete_record(db, await _readable(db, record_id, user, held, lock=True))
    return {"message": "As-built record deleted"}


@router.post(
    "/{record_id}/survey",
    response_model=AsBuiltRead,
    summary="Record a Survey",
    description="While the record is draft or surveyed, so a survey can be repeated. Stores the measured value given "
    "(else the stored one is judged again) and the tolerance result, sets the surveyed-by user when empty, and raises "
    "no report.",
    dependencies=UPDATE,
)
async def survey_record(
    record_id: Id, values: AsBuiltSurvey, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    record = await _readable(db, record_id, user, held, lock=True)
    return await service.survey_record(db, record, values.model_dump(), user["id"])


@router.post(
    "/{record_id}/verify",
    response_model=AsBuiltRead,
    summary="Verify an As-Built Record",
    description="Only a surveyed record. An out-of-tolerance result raises a workmanship report (default major) and "
    "stores its identifier; within and not assessed raise nothing. The legal-record flag is not set.",
    dependencies=REVIEW,
)
async def verify_record(
    record_id: Id, values: AsBuiltVerify, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    record = await _readable(db, record_id, user, held, lock=True)
    return await service.verify_record(db, record, user_id=user["id"], notes=values.notes, severity=values.severity)


@router.post(
    "/{record_id}/sign",
    response_model=AsBuiltRead,
    summary="Sign the Legal-Record Attestation",
    description="Only a verified record. Valid sets the legal-record flag, stores the signer, time, network address and "
    "a digest, and moves the record to recorded. Not valid stores the same signature data and leaves the record "
    "verified with the flag false.",
    dependencies=APPROVE,
)
async def sign_record(
    record_id: Id,
    values: AsBuiltSign,
    request: Request,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    record = await _readable(db, record_id, user, held, lock=True)
    return await service.sign_record(
        db,
        record,
        user_id=user["id"],
        valid=values.valid,
        notes=values.notes,
        signed_at=values.signed_at,
        ip=request.client.host if request.client else None,
    )
