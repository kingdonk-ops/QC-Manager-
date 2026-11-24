"""Signatory status and the additional-signatory action on an ITP line. Included by the main inspections router before
the integer-id routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Path

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID
from ..projects.service import readable_project
from . import eligibility, service, signatories
from .models import Inspection
from .permissions import InspectionPermissionName as P
from .signatory_schemas import AdditionalSignatory, SignatoryStatus

router = APIRouter(tags=["Quality Inspections"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]
SIGN = [require_permissions(P.SUBMIT.value)]


async def _readable(
    db: Any, inspection_id: int, user: dict[str, Any], held: frozenset[str], *, lock: bool = False
) -> Inspection:
    """The record once the caller may see its project (a foreign project answers not-found). ``lock`` re-reads it under
    a row lock, so two simultaneous signatures on one line run one after the other."""
    inspection = await service.get_inspection(db, inspection_id)
    await readable_project(db, inspection.project_id, user["id"], held)
    if lock:
        await db.refresh(inspection, with_for_update=True)
    return inspection


@router.get(
    "/{inspection_id}/signatories",
    response_model=SignatoryStatus,
    summary="Signatory Status of a Line",
    description="Read-only. The required signatory count, how many distinct people have signed the current content, who "
    "they are with their roles, and whether the requirement is met. One person signing twice counts once; provisional, "
    "void and rejected signatures, signatures over changed content and the hold release do not count.",
    dependencies=READ,
)
async def signatory_status(inspection_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    inspection = await _readable(db, inspection_id, user, held)
    return await signatories.status_of(db, inspection)


@router.post(
    "/{inspection_id}/signatories/additional",
    response_model=SignatoryStatus,
    status_code=201,
    summary="Sign as an Additional Signatory",
    description="Adds the caller's signature over the current content in the additional-signatory role, one per person "
    "and role (a second submission by the same person is a conflict, also when two arrive together). ITP lines only; "
    "refused for a planned, passed or failed line and until the inspector has signed. Answers with the new status.",
    dependencies=SIGN,
)
async def add_additional_signatory(
    inspection_id: Id, values: AdditionalSignatory, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    inspection = await _readable(db, inspection_id, user, held, lock=True)
    await signatories.add_additional_signatory(
        db,
        inspection,
        user["id"],
        held,
        accept_intent=values.accept_intent,
        sign_findings=lambda: eligibility.check(db, inspection, "sign", user_id=user["id"]),
    )
    return await signatories.status_of(db, inspection)
