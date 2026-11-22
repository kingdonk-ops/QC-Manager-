"""Inspection requests (call-outs): /api/v1/inspections/requests."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import callouts
from .constants import RequestStatus
from .models import InspectionRequest, RequestLink
from .permissions import InspectionPermissionName as P
from .quality_schemas import (
    CalloutAcknowledge,
    CalloutAttendance,
    CalloutCalendarEvent,
    CalloutCancel,
    CalloutConfirm,
    CalloutCreate,
    CalloutOutcome,
    CalloutRead,
    CalloutRecipientDelivery,
    CalloutReschedule,
    CalloutUpdate,
    CalloutWaive,
)

router = APIRouter(prefix="/requests", tags=["Quality Inspections: requests"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQuery = Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)]
READ = [require_permissions(P.READ.value)]


async def _readable(db: Any, request_id: int, user: dict[str, Any], held: frozenset[str]) -> InspectionRequest:
    r = await callouts.get_request(db, request_id)
    await readable_project(db, r.project_id, user["id"], held)
    return r


async def _one(db: Any, r: InspectionRequest, findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    out = (await callouts.read_requests(db, [r]))[0]
    out["findings"] = findings or []
    return out


@router.get(
    "/calendar",
    response_model=list[CalloutCalendarEvent],
    summary="Inspection Request Calendar",
    description="One event per request scheduled in `[from, to)` (at most 62 days): status, time window, strongest "
    "external point, and per external H/W party its attendance and notice delivery. `mine=true`: requests you "
    "raised, witness or receive.",
    dependencies=READ,
)
async def calendar(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
    mine: bool = False,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    if end <= start or end - start > timedelta(days=62):
        raise UnprocessableEntityException("Pick a range of at most 62 days.")
    return await callouts.calendar(
        db, project_id, start, end, mine_user_id=user["id"] if mine else None, include_drafts=P.CREATE in held
    )


@router.get(
    "/",
    response_model=PaginatedListResponse[CalloutRead],
    summary="List Inspection Requests",
    description="Newest scheduled first. Filter by status, or `open=true` for requested and confirmed call-outs.",
    dependencies=READ,
)
async def list_requests(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: ProjectQuery,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    status: RequestStatus | None = None,
    open: bool = False,
    inspection_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [InspectionRequest.project_id == project_id]
    if P.CREATE not in held:
        where.append(InspectionRequest.status != RequestStatus.DRAFT)
    if status:
        where.append(InspectionRequest.status == status.value)
    if open:
        where.append(InspectionRequest.status.in_((RequestStatus.REQUESTED.value, RequestStatus.CONFIRMED.value)))
    if inspection_id:
        where.append(InspectionRequest.id.in_(select(RequestLink.request_id).where(RequestLink.inspection_id == inspection_id)))
    total = await db.scalar(select(func.count()).select_from(InspectionRequest).where(*where))
    rows = list(
        (
            await db.execute(
                select(InspectionRequest)
                .where(*where)
                .order_by(InspectionRequest.scheduled_start.desc(), InspectionRequest.id.desc())
                .offset(compute_offset(page, items_per_page))
                .limit(items_per_page)
            )
        ).scalars()
    )
    data = {"data": await callouts.read_requests(db, rows), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/",
    response_model=CalloutRead,
    status_code=201,
    summary="Draft an Inspection Request",
    description="Links ITP lines or QA inspections (each on at most one live request). Each party's point defaults to "
    "the strongest of the linked lines; name a witness, account recipients and contacts per party.",
    dependencies=[require_permissions(P.CREATE.value)],
)
async def create(values: CalloutCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    body = values.model_dump(exclude={"project_id"})
    body["parties"] = [p.model_dump(mode="json") for p in values.parties]
    r = await callouts.create(db, values.project_id, body, user["id"])
    return await _one(db, r)


@router.get("/{request_id}", response_model=CalloutRead, summary="An Inspection Request", dependencies=READ)
async def get(request_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    r = await _readable(db, request_id, user, held)
    if r.status == RequestStatus.DRAFT and P.CREATE not in held:
        raise callouts.RequestNotFoundError("Draft")
    return await _one(db, r)


@router.patch(
    "/{request_id}",
    response_model=CalloutRead,
    summary="Edit a Draft Request",
    dependencies=[require_permissions(P.CREATE.value)],
)
async def update(
    request_id: Id, values: CalloutUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.update_draft(db, r, values.model_dump(exclude_unset=True))
    return await _one(db, r)


@router.post(
    "/{request_id}/issue",
    response_model=CalloutRead,
    summary="Issue the Request",
    description="Allocates the number (IR-001), computes the notice (the project's minimum, 24 h by default, when "
    "an external party has a Hold or Witness point; short notice is a warning in `findings` unless the project blocks "
    "it), moves the linked records to `requested` and sends the call-out to every recipient, in-app and by e-mail, "
    "whatever their notification preferences. Refused while a linked ITP line sits behind an unreleased Hold.",
    dependencies=[require_permissions(P.CREATE.value)],
)
async def issue(request_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    r = await _readable(db, request_id, user, held)
    findings = await callouts.issue(db, r, user["id"])
    return await _one(db, r, findings)


@router.post(
    "/{request_id}/confirm",
    response_model=CalloutRead,
    summary="Confirm the Call-out",
    description="By a named witness (or their delegate), the client (`inspections.respond`), or a reviewer recording "
    "it on the party's behalf with a reference.",
    dependencies=READ,
)
async def confirm(
    request_id: Id, values: CalloutConfirm, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.confirm(db, r, user["id"], held, values.confirmation_ref)
    return await _one(db, r)


@router.post(
    "/{request_id}/acknowledge",
    response_model=CalloutRead,
    summary="Acknowledge the Call-out",
    description="A recipient acknowledges their own notice; a reviewer may record a contact's acknowledgement.",
    dependencies=READ,
)
async def acknowledge(
    request_id: Id, values: CalloutAcknowledge, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.acknowledge(db, r, user["id"], held, values.recipient_id)
    return await _one(db, r)


@router.post(
    "/{request_id}/recipients/{recipient_id}/delivery",
    response_model=CalloutRead,
    summary="Record a Delivery Result",
    description="A bounce or late delivery for one recipient. A party whose every recipient failed has no valid "
    "notice; the effect is frozen when the outcome is recorded, so a later result never changes it.",
    dependencies=[require_permissions(P.REVIEW.value)],
)
async def delivery(
    request_id: Id,
    recipient_id: Id,
    values: CalloutRecipientDelivery,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.record_delivery(db, r, recipient_id, values.delivery.value, values.reason)
    return await _one(db, r)


@router.post(
    "/{request_id}/attendance",
    response_model=CalloutRead,
    summary="Record a Party's Attendance",
    description="A named witness records their own `attended`; a reviewer records `attended` or `absent` for any "
    "party with a Hold or Witness point.",
    dependencies=READ,
)
async def attendance(
    request_id: Id, values: CalloutAttendance, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.attendance(db, r, values.party.value, values.attendance, user["id"], held)
    return await _one(db, r)


@router.post(
    "/{request_id}/waive",
    response_model=CalloutRead,
    summary="Waive a Party's Attendance",
    description="The party itself (the client with `inspections.respond`, or the named witness) waives any point; a "
    "reviewer only a Witness point, citing the party's written waiver. When every external H/W party has waived, the "
    "request becomes `waived` and the work may proceed.",
    dependencies=READ,
)
async def waive(
    request_id: Id, values: CalloutWaive, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.waive(db, r, values.party.value, values.waiver_ref, user["id"], held)
    return await _one(db, r)


@router.post(
    "/{request_id}/outcome",
    response_model=CalloutRead,
    summary="Record the Outcome",
    description="`witnessed` (nobody pending, nobody absent, someone attended), `no_show` (after the grace period, "
    "someone absent: the work proceeds only when every absent party had a Witness point and valid notice) or "
    "`failed` (with a reason: work not ready, access, weather...). Each party's notice validity is frozen now.",
    dependencies=[require_permissions(P.REVIEW.value)],
)
async def outcome(
    request_id: Id, values: CalloutOutcome, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.outcome(
        db, r, values.outcome.value, user["id"], reason=values.reason, note=values.note, occurred_at=values.occurred_at
    )
    return await _one(db, r)


@router.post(
    "/{request_id}/reschedule",
    response_model=CalloutRead,
    summary="Reschedule",
    description="From requested, confirmed, no_show or failed back to requested at a new future time, keeping the "
    "history: confirmation, attendance and delivery are reset, notice recomputed and the call-out sent again.",
    dependencies=READ,
)
async def reschedule(
    request_id: Id, values: CalloutReschedule, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    findings = await callouts.reschedule(db, r, values.scheduled_start, values.reason, user["id"], held)
    return await _one(db, r, findings)


@router.post(
    "/{request_id}/cancel",
    response_model=CalloutRead,
    summary="Cancel",
    description="A draft, requested or confirmed request. The linked records go back to their earlier status when no "
    "other open request holds them. An issued request keeps its number.",
    dependencies=[require_permissions(P.CREATE.value)],
)
async def cancel(
    request_id: Id, values: CalloutCancel, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await _readable(db, request_id, user, held)
    await callouts.cancel(db, r, values.reason, user["id"])
    return await _one(db, r)


@router.get("/{request_id}/history", summary="Request History", dependencies=READ)
async def history(
    request_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    return await callouts.history(db, await _readable(db, request_id, user, held))
