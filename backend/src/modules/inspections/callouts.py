"""Requests for Inspection (call-outs; KERP ``inspection_requests``, TD-045), one inspection event per request.

``draft → requested`` (issue: number, notice, linked records → ``requested``, call-out notices) ``→ confirmed →
witnessed | waived | no_show | failed``; reschedule returns to ``requested`` keeping history; cancel reverts the
linked records. Per party: intervention point, attendance, waiver and the validity of its notice, frozen when
the outcome is recorded. Per recipient: delivery and acknowledgement. Call-out notices are transactional: a
recipient's notification opt-out never suppresses them.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnprocessableEntityException,
)
from ...infrastructure.mail import Mail, deliver
from ...infrastructure.records import history_of, next_reference, record_transition
from ..asset_tree import service as tree
from ..common.exceptions import ResourceNotFoundError
from ..contacts.service import contact_emails, contact_names
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from . import eligibility, signing
from .constants import (
    EXTERNAL_PARTIES,
    LIVE_REQUEST,
    OPEN_REQUEST,
    POINT_STRENGTH,
    Attendance,
    DelegationKind,
    Delivery,
    InspectionStatus,
    Kind,
    Outcome,
    Party,
    RequestStatus,
)
from .models import Inspection, InspectionRequest, RequestLink, RequestParty, RequestRecipient
from .permissions import InspectionPermissionName as P
from .service import ENTITY, user_names

REQUEST_ENTITY = "inspection_request"


class RequestNotFoundError(ResourceNotFoundError):
    public_detail = "Inspection request not found."


def now() -> datetime:
    return datetime.now(UTC)


def link_of(r: InspectionRequest) -> str:
    return f"/inspections/requests?project={r.project_id}&id={r.id}"


async def get_request(db: AsyncSession, request_id: int) -> InspectionRequest:
    r = await db.get(InspectionRequest, request_id)
    if r is None:
        raise RequestNotFoundError("No such request")
    return r


async def links_of(db: AsyncSession, request_id: int) -> list[RequestLink]:
    return list((await db.execute(select(RequestLink).where(RequestLink.request_id == request_id))).scalars())


async def parties_of(db: AsyncSession, request_id: int) -> list[RequestParty]:
    rows = await db.execute(select(RequestParty).where(RequestParty.request_id == request_id).order_by(RequestParty.id))
    return list(rows.scalars())


async def recipients_of(db: AsyncSession, request_id: int) -> list[RequestRecipient]:
    rows = await db.execute(
        select(RequestRecipient).where(RequestRecipient.request_id == request_id).order_by(RequestRecipient.id)
    )
    return list(rows.scalars())


def party_delivery(party: RequestParty, recipients: list[RequestRecipient]) -> tuple[str, str | None]:
    """``failed`` when every attempt for the party failed (or nobody can be reached), ``delivered`` once one
    succeeded, else ``pending``."""
    mine = [r for r in recipients if r.party == party.party]
    if not mine:
        return Delivery.FAILED.value, "no_channel"
    if any(r.delivery == Delivery.DELIVERED for r in mine):
        return Delivery.DELIVERED.value, None
    if all(r.delivery == Delivery.FAILED for r in mine):
        return Delivery.FAILED.value, mine[-1].delivery_reason
    return Delivery.PENDING.value, None


def strongest(points: list[str]) -> str:
    return max(points, key=lambda p: POINT_STRENGTH.get(p, 0)) if points else "none"


# --- reading -----------------------------------------------------------------------------------------


async def read_requests(db: AsyncSession, requests: list[InspectionRequest], *, detail: bool = False) -> list[dict[str, Any]]:
    out = []
    for r in requests:
        parties = await parties_of(db, r.id)
        recipients = await recipients_of(db, r.id)
        links = await links_of(db, r.id)
        inspections = {
            i.id: i
            for i in (
                await db.execute(select(Inspection).where(Inspection.id.in_([lk.inspection_id for lk in links])))
            ).scalars()
        }
        names = await user_names(
            db,
            {r.requested_by_id}
            | {p.witness_user_id for p in parties}
            | {x.user_id for x in recipients}
            | {x.on_behalf_of_user_id for x in recipients},
        )
        contacts = await contact_names(db, {x.contact_id for x in recipients if x.contact_id})
        ext = {p.party: p.point for p in parties if p.party in EXTERNAL_PARTIES and p.point in ("H", "W")}
        item: dict[str, Any] = {
            "id": r.id,
            "project_id": r.project_id,
            "code": r.code,
            "title": r.title,
            "discipline": r.discipline,
            "status": r.status,
            "scheduled_start": r.scheduled_start,
            "scheduled_end": r.scheduled_start + timedelta(minutes=r.duration_minutes),
            "duration_minutes": r.duration_minutes,
            "location_ref": r.location_ref,
            "location_node_id": r.location_node_id,
            "notes": r.notes,
            "requested_by_id": r.requested_by_id,
            "requested_by_name": names.get(r.requested_by_id or 0),
            "issued_at": r.issued_at,
            "required_notice_hours": r.required_notice_hours,
            "notice_given_at": r.notice_given_at,
            "notice_met": r.notice_met,
            "reschedule_count": r.reschedule_count,
            "confirmed_by_id": r.confirmed_by_id,
            "confirmed_at": r.confirmed_at,
            "outcome_by_id": r.outcome_by_id,
            "outcome_at": r.outcome_at,
            "outcome_reason": r.outcome_reason,
            "outcome_note": r.outcome_note,
            "cancelled_reason": r.cancelled_reason,
            "strongest_point": strongest(list(ext.values())),
            "inspections": [
                {
                    "id": i.id,
                    "code": i.code,
                    "title": i.title,
                    "kind": i.kind,
                    "status": i.status,
                    "result": i.result,
                    "points": i.points,
                    "prior_status": lk.prior_status,
                }
                for lk in links
                if (i := inspections.get(lk.inspection_id))
            ],
            "parties": [],
        }
        for p in parties:
            delivery, reason = party_delivery(p, recipients)
            mine = [x for x in recipients if x.party == p.party]
            item["parties"].append(
                {
                    "id": p.id,
                    "party": p.party,
                    "point": p.point,
                    "point_source": p.point_source,
                    "external_hw": p.party in EXTERNAL_PARTIES and p.point in ("H", "W"),
                    "witness_user_id": p.witness_user_id,
                    "witness_name": names.get(p.witness_user_id or 0),
                    "attendance": p.attendance,
                    "attendance_at": p.attendance_at,
                    "waiver_ref": p.waiver_ref,
                    "notice_delivery": delivery,
                    "notice_delivery_reason": reason,
                    "notice_valid_at_outcome": p.notice_valid_at_outcome,
                    "acknowledged": bool(mine) and all(x.acknowledged_at for x in mine),
                    "recipients": [
                        {
                            "id": x.id,
                            "user_id": x.user_id,
                            "contact_id": x.contact_id,
                            "name": names.get(x.user_id or 0) if x.user_id else contacts.get(x.contact_id or 0),
                            "on_behalf_of_user_id": x.on_behalf_of_user_id,
                            "on_behalf_of_name": names.get(x.on_behalf_of_user_id or 0),
                            "delivery": x.delivery,
                            "delivery_reason": x.delivery_reason,
                            "delivered_at": x.delivered_at,
                            "acknowledged_at": x.acknowledged_at,
                        }
                        for x in mine
                    ],
                }
            )
        out.append(item)
    return out


async def latest_request_summary(db: AsyncSession, inspection_id: int) -> dict[str, Any] | None:
    r = await db.scalar(
        select(InspectionRequest)
        .join(RequestLink, RequestLink.request_id == InspectionRequest.id)
        .where(RequestLink.inspection_id == inspection_id)
        .order_by(InspectionRequest.id.desc())
        .limit(1)
    )
    if r is None:
        return None
    return {"id": r.id, "code": r.code, "status": r.status, "scheduled_start": r.scheduled_start}


# --- drafting ----------------------------------------------------------------------------------------


async def _check_links(
    db: AsyncSession, project_id: int, inspection_ids: list[int], request_id: int | None
) -> list[Inspection]:
    rows = {i.id: i for i in (await db.execute(select(Inspection).where(Inspection.id.in_(inspection_ids)))).scalars()}
    found = []
    for iid in dict.fromkeys(inspection_ids):
        i = rows.get(iid)
        if i is None or i.project_id != project_id:
            raise NotFoundException(f"Inspection {iid} not found.")
        if i.kind != Kind.ITP and i.category != "qa_itp":
            raise UnprocessableEntityException(f"{i.code} is a project-level record; only QA/ITP records are called out.")
        live = await db.scalar(
            select(InspectionRequest.id)
            .join(RequestLink, RequestLink.request_id == InspectionRequest.id)
            .where(
                RequestLink.inspection_id == iid,
                InspectionRequest.status.in_(LIVE_REQUEST),
                InspectionRequest.id != (request_id or 0),
            )
        )
        if live:
            raise ConflictException(f"{i.code} is already on a live inspection request.")
        found.append(i)
    return found


async def create(db: AsyncSession, project_id: int, values: dict[str, Any], user_id: int) -> InspectionRequest:
    inspections = await _check_links(db, project_id, values.pop("inspection_ids"), None)
    parties_in = {p["party"]: p for p in values.pop("parties", [])}
    if values.get("location_node_id"):
        await tree.get_node(db, values["location_node_id"], project_id)
    r = InspectionRequest(project_id=project_id, requested_by_id=user_id, status=RequestStatus.DRAFT.value, **values)
    db.add(r)
    await db.flush()
    for i in inspections:
        db.add(RequestLink(request_id=r.id, inspection_id=i.id))
    # Points default from the linked lines: the strongest per party.
    for name in Party:
        from_itp = strongest([i.points.get(name.value, "none") for i in inspections])
        given = parties_in.get(name.value, {})
        point = str(given.get("point") or from_itp)
        if point == "none" and not given:
            continue
        p = RequestParty(
            request_id=r.id,
            party=name.value,
            point=point,
            point_source="manual" if given.get("point") and given["point"] != from_itp else "itp",
            witness_user_id=given.get("witness_user_id"),
        )
        db.add(p)
        users = set(given.get("recipient_user_ids") or []) | ({p.witness_user_id} if p.witness_user_id else set())
        for uid in sorted(users):
            db.add(RequestRecipient(request_id=r.id, party=name.value, user_id=uid))
        for cid in dict.fromkeys(given.get("contact_ids") or []):
            db.add(RequestRecipient(request_id=r.id, party=name.value, contact_id=cid))
    await record_transition(db, REQUEST_ENTITY, r.id, None, r.status, user_id)
    await db.commit()
    return r


async def update_draft(db: AsyncSession, r: InspectionRequest, changes: dict[str, Any]) -> None:
    if r.status != RequestStatus.DRAFT:
        raise UnprocessableEntityException("Only a draft request is edited; reschedule or cancel an issued one.")
    if "inspection_ids" in changes:
        inspections = await _check_links(db, r.project_id, changes.pop("inspection_ids"), r.id)
        await db.execute(delete(RequestLink).where(RequestLink.request_id == r.id))
        for i in inspections:
            db.add(RequestLink(request_id=r.id, inspection_id=i.id))
    for key, value in changes.items():
        setattr(r, key, value)
    await db.commit()


# --- issue, notices ----------------------------------------------------------------------------------


def _notice(r: InspectionRequest, ext: dict[str, str], min_hours: int) -> list[eligibility.Finding]:
    r.required_notice_hours = min_hours if ext else 0
    r.notice_given_at = now()
    r.notice_met = (r.scheduled_start - r.notice_given_at) >= timedelta(hours=r.required_notice_hours)
    if r.notice_met:
        return []
    return [
        eligibility.Finding(
            "NOTICE_SHORT",
            f"Short notice: {r.required_notice_hours} h are required for a Hold or Witness call-out. A party that "
            "stays away after short notice never lets the work proceed.",
            blocking=False,
        )
    ]


def _future(start: datetime) -> None:
    if start <= now():
        raise UnprocessableEntityException("The inspection must be scheduled in the future.")


async def _add_delegates(db: AsyncSession, r: InspectionRequest, parties: list[RequestParty]) -> None:
    """Call-outs to a named witness also go to their active delegate for hold points."""
    recipients = await recipients_of(db, r.id)
    have = {(x.party, x.user_id) for x in recipients}
    for p in parties:
        if not p.witness_user_id:
            continue
        d = await signing.active_delegation(db, r.project_id, p.witness_user_id, DelegationKind.HOLD_POINT)
        if d and (p.party, d.delegate_id) not in have:
            db.add(
                RequestRecipient(request_id=r.id, party=p.party, user_id=d.delegate_id, on_behalf_of_user_id=p.witness_user_id)
            )
    await db.flush()


async def _send_callout(db: AsyncSession, r: InspectionRequest, event: str, actor_id: int) -> None:
    """Notify every recipient (transactional: preferences are ignored) and record delivery per recipient."""
    project = await db.get(Project, r.project_id)
    recipients = await recipients_of(db, r.id)
    when = r.scheduled_start.strftime("%Y-%m-%d %H:%M UTC")
    title = f"{r.code or 'Inspection request'} {event}: {r.title}"[:300]
    body = f"{project.code if project else ''} — scheduled {when}" + (f", {r.location_ref}" if r.location_ref else "")
    users = [x.user_id for x in recipients if x.user_id]
    await notify(
        db,
        users,
        Category.APPROVAL,
        title,
        body=body,
        link=link_of(r),
        entity=(REQUEST_ENTITY, r.id),
        transactional=True,
    )
    emails = await contact_emails(db, [x.contact_id for x in recipients if x.contact_id])
    for x in recipients:
        x.acknowledged_at = None
        x.acknowledged_by_id = None
        if x.user_id:
            x.delivery, x.delivery_reason, x.delivered_at = Delivery.DELIVERED.value, None, now()
        elif x.contact_id and emails.get(x.contact_id):
            await deliver(Mail(to=[emails[x.contact_id]], subject=title[:200], text=f"{title}\n\n{body}"))
            x.delivery, x.delivery_reason, x.delivered_at = Delivery.DELIVERED.value, None, now()
        else:
            x.delivery, x.delivery_reason = Delivery.FAILED.value, "no_channel"


async def issue(db: AsyncSession, r: InspectionRequest, user_id: int) -> list[dict[str, Any]]:
    if r.status != RequestStatus.DRAFT:
        raise UnprocessableEntityException("Only a draft request is issued.")
    _future(r.scheduled_start)
    links = await links_of(db, r.id)
    if not links:
        raise UnprocessableEntityException("Link at least one ITP line or QA inspection.")
    inspections = list(
        (await db.execute(select(Inspection).where(Inspection.id.in_([lk.inspection_id for lk in links])))).scalars()
    )
    blocking: list[str] = []
    for i in inspections:
        for f in await eligibility.check(db, i, "request"):
            if f.blocking:
                blocking.append(f"{i.code}: {f.code}: {f.message}")
    if blocking:
        raise UnprocessableEntityException("; ".join(blocking))
    parties = await parties_of(db, r.id)
    ext = {p.party: p.point for p in parties if p.party in EXTERNAL_PARTIES and p.point in ("H", "W")}
    settings = await eligibility.settings_of(db, r.project_id)
    findings = _notice(r, ext, settings.min_notice_hours)
    if findings and settings.block_short_notice:
        raise UnprocessableEntityException(findings[0].message)
    r.code = await next_reference(db, "IR", r.project_id)
    r.issued_at = now()
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, RequestStatus.REQUESTED, user_id)
    r.status = RequestStatus.REQUESTED.value
    by_id = {i.id: i for i in inspections}
    for lk in links:
        i = by_id[lk.inspection_id]
        lk.prior_status = i.status
        await record_transition(db, ENTITY, i.id, i.status, InspectionStatus.REQUESTED, user_id, note=r.code)
        i.status = InspectionStatus.REQUESTED.value
        i.scheduled_date = r.scheduled_start.date()
    await _add_delegates(db, r, parties)
    await _send_callout(db, r, "issued", user_id)
    await db.commit()
    return [f.dump() for f in findings]


# --- actions after issue -----------------------------------------------------------------------------


def _open(r: InspectionRequest) -> None:
    if r.status not in OPEN_REQUEST:
        raise UnprocessableEntityException(f"The request is {r.status.replace('_', ' ')}.")


async def _party(db: AsyncSession, r: InspectionRequest, name: str) -> RequestParty:
    p = await db.scalar(select(RequestParty).where(RequestParty.request_id == r.id, RequestParty.party == name))
    if p is None:
        raise NotFoundException(f"No {name.replace('_', ' ')} party on this request.")
    return p


async def _is_witness(db: AsyncSession, r: InspectionRequest, p: RequestParty, user_id: int) -> bool:
    if p.witness_user_id == user_id:
        return True
    if p.witness_user_id:
        d = await signing.active_delegation(db, r.project_id, p.witness_user_id, DelegationKind.HOLD_POINT)
        return bool(d and d.delegate_id == user_id)
    return False


async def confirm(db: AsyncSession, r: InspectionRequest, user_id: int, held: frozenset[str], ref: str | None) -> None:
    if r.status != RequestStatus.REQUESTED:
        raise UnprocessableEntityException("Only a requested call-out is confirmed.")
    witness = any([await _is_witness(db, r, p, user_id) for p in await parties_of(db, r.id)])
    if not witness and P.RESPOND not in held:
        if P.REVIEW not in held:
            raise ForbiddenException("Only a named witness, the client or a reviewer confirms a call-out.")
        if not ref:
            raise UnprocessableEntityException("Recording a confirmation on someone's behalf needs a reference.")
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, RequestStatus.CONFIRMED, user_id, ref)
    r.status = RequestStatus.CONFIRMED.value
    r.confirmed_by_id, r.confirmed_at = user_id, now()
    await notify(
        db,
        [r.requested_by_id or 0],
        Category.STATUS,
        f"{r.code} confirmed",
        link=link_of(r),
        entity=(REQUEST_ENTITY, r.id),
        actor_id=user_id,
    )
    await db.commit()


async def acknowledge(
    db: AsyncSession, r: InspectionRequest, user_id: int, held: frozenset[str], recipient_id: int | None
) -> None:
    """A recipient acknowledges their own call-out; a reviewer may record a contact's acknowledgement."""
    if r.status not in OPEN_REQUEST:
        raise UnprocessableEntityException("Only an open call-out is acknowledged.")
    recipients = await recipients_of(db, r.id)
    if recipient_id is not None:
        target = [x for x in recipients if x.id == recipient_id]
        if not target:
            raise NotFoundException("No such recipient on this request.")
        if target[0].user_id != user_id and P.REVIEW not in held:
            raise ForbiddenException("Only reviewers record someone else's acknowledgement.")
    else:
        target = [x for x in recipients if x.user_id == user_id]
        if not target:
            raise ForbiddenException("You aren't a recipient of this call-out.")
    for x in target:
        x.acknowledged_at, x.acknowledged_by_id = now(), user_id
    await db.commit()


async def record_delivery(db: AsyncSession, r: InspectionRequest, recipient_id: int, delivery: str, reason: str | None) -> None:
    """A delivery result reported later (e.g. a bounce). Never changes an outcome already recorded."""
    x = await db.get(RequestRecipient, recipient_id)
    if x is None or x.request_id != r.id:
        raise NotFoundException("No such recipient on this request.")
    x.delivery, x.delivery_reason = delivery, reason
    if delivery == Delivery.DELIVERED:
        x.delivered_at = now()
    await db.commit()


async def attendance(
    db: AsyncSession, r: InspectionRequest, party: str, value: str, user_id: int, held: frozenset[str]
) -> None:
    _open(r)
    p = await _party(db, r, party)
    if not (p.party in EXTERNAL_PARTIES and p.point in ("H", "W")):
        raise UnprocessableEntityException("Attendance is recorded for parties with a Hold or Witness point.")
    if P.REVIEW not in held:
        if not (value == Attendance.ATTENDED and await _is_witness(db, r, p, user_id)):
            raise ForbiddenException("A witness records only their own attendance; reviewers record any.")
    p.attendance, p.attendance_by_id, p.attendance_at = value, user_id, now()
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, r.status, user_id, f"{party}: {value}")
    await db.commit()


async def waive(
    db: AsyncSession, r: InspectionRequest, party: str, waiver_ref: str | None, user_id: int, held: frozenset[str]
) -> None:
    """The party waives its attendance. The client (``respond``) may waive any point; a reviewer only a Witness
    point, citing the party's written waiver. When every external H/W party has waived, the request is waived."""
    _open(r)
    p = await _party(db, r, party)
    if not (p.party in EXTERNAL_PARTIES and p.point in ("H", "W")):
        raise UnprocessableEntityException("Only a party with a Hold or Witness point waives.")
    own = (party == Party.CLIENT and P.RESPOND in held) or await _is_witness(db, r, p, user_id)
    if not own:
        if P.REVIEW not in held:
            raise ForbiddenException("Only the party, or a reviewer with the party's written waiver, waives.")
        if p.point != "W":
            raise ForbiddenException("Only the party itself waives a Hold point.")
        if not waiver_ref:
            raise UnprocessableEntityException("Cite the party's written waiver (waiver_ref).")
    p.attendance, p.attendance_by_id, p.attendance_at, p.waiver_ref = Attendance.WAIVED.value, user_id, now(), waiver_ref
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, r.status, user_id, f"{party} waived {waiver_ref or ''}".strip())
    parties = await parties_of(db, r.id)
    ext = [x for x in parties if x.party in EXTERNAL_PARTIES and x.point in ("H", "W")]
    if all(x.attendance == Attendance.WAIVED for x in ext):
        recipients = await recipients_of(db, r.id)
        _freeze_notice(r, ext, recipients)
        await record_transition(db, REQUEST_ENTITY, r.id, r.status, RequestStatus.WAIVED, user_id)
        r.status = RequestStatus.WAIVED.value
        r.outcome_by_id, r.outcome_at = user_id, now()
        await _notify_requester(db, r, "waived", user_id)
    await db.commit()


def _freeze_notice(r: InspectionRequest, ext: list[RequestParty], recipients: list[RequestRecipient]) -> None:
    """Valid notice per party = the request's notice was met and the party's call-out wasn't undeliverable."""
    for p in ext:
        delivery, _ = party_delivery(p, recipients)
        p.notice_valid_at_outcome = bool(r.notice_met) and delivery != Delivery.FAILED


async def outcome(
    db: AsyncSession,
    r: InspectionRequest,
    value: str,
    user_id: int,
    *,
    reason: str | None,
    note: str | None,
    occurred_at: datetime | None,
) -> None:
    _open(r)
    at = occurred_at or now()
    parties = await parties_of(db, r.id)
    ext = [p for p in parties if p.party in EXTERNAL_PARTIES and p.point in ("H", "W")]
    pending = [p.party for p in ext if p.attendance == Attendance.PENDING]
    if value in (Outcome.WITNESSED, Outcome.NO_SHOW) and pending:
        raise UnprocessableEntityException(f"ATTENDANCE_PENDING: record attendance for {', '.join(pending)} first.")
    if value == Outcome.WITNESSED:
        if any(p.attendance == Attendance.ABSENT for p in ext):
            raise UnprocessableEntityException("A party was absent: record a no-show, not witnessed.")
        if ext and not any(p.attendance == Attendance.ATTENDED for p in ext):
            raise UnprocessableEntityException("Nobody attended: the request is waived, not witnessed.")
    elif value == Outcome.NO_SHOW:
        settings = await eligibility.settings_of(db, r.project_id)
        if at < r.scheduled_start + timedelta(minutes=settings.no_show_grace_minutes):
            raise UnprocessableEntityException(
                f"A no-show is recorded {settings.no_show_grace_minutes} min after the scheduled start at the earliest."
            )
        if not any(p.attendance == Attendance.ABSENT for p in ext):
            raise UnprocessableEntityException("A no-show needs at least one absent party.")
    elif value == Outcome.FAILED and not (reason or "").strip():
        raise UnprocessableEntityException("Say why the inspection couldn't be held (reason).")
    _freeze_notice(r, ext, await recipients_of(db, r.id))
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, value, user_id, note or reason)
    r.status = value
    r.outcome_by_id, r.outcome_at, r.outcome_reason, r.outcome_note = user_id, at, reason, note
    await _notify_requester(db, r, value.replace("_", " "), user_id)
    await db.commit()


async def _notify_requester(db: AsyncSession, r: InspectionRequest, event: str, actor_id: int) -> None:
    await notify(
        db,
        [r.requested_by_id or 0],
        Category.STATUS,
        f"{r.code}: {event}",
        link=link_of(r),
        entity=(REQUEST_ENTITY, r.id),
        actor_id=actor_id,
    )


async def reschedule(
    db: AsyncSession, r: InspectionRequest, start: datetime, reason: str, user_id: int, held: frozenset[str]
) -> list[dict[str, Any]]:
    if r.status not in (*OPEN_REQUEST, RequestStatus.NO_SHOW, RequestStatus.FAILED):
        raise UnprocessableEntityException(f"A {r.status.replace('_', ' ')} request isn't rescheduled.")
    if P.CREATE not in held and P.RESPOND not in held:
        raise ForbiddenException("Only the requester's side or the client reschedules.")
    _future(start)
    old = r.scheduled_start
    r.scheduled_start = start
    r.reschedule_count += 1
    r.confirmed_by_id = r.confirmed_at = None
    r.outcome_by_id = r.outcome_at = r.outcome_reason = r.outcome_note = None
    parties = await parties_of(db, r.id)
    for p in parties:
        p.attendance, p.attendance_by_id, p.attendance_at, p.waiver_ref = Attendance.PENDING.value, None, None, None
        p.notice_valid_at_outcome = None
    ext = {p.party: p.point for p in parties if p.party in EXTERNAL_PARTIES and p.point in ("H", "W")}
    settings = await eligibility.settings_of(db, r.project_id)
    findings = _notice(r, ext, settings.min_notice_hours)
    if findings and settings.block_short_notice:
        raise UnprocessableEntityException(findings[0].message)
    note = f"Rescheduled from {old.isoformat()} to {start.isoformat()}: {reason}"
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, RequestStatus.REQUESTED, user_id, note)
    r.status = RequestStatus.REQUESTED.value
    for lk in await links_of(db, r.id):
        i = await db.get(Inspection, lk.inspection_id)
        if i is not None and i.status == InspectionStatus.REQUESTED:
            i.scheduled_date = start.date()
    await _add_delegates(db, r, parties)
    await _send_callout(db, r, "rescheduled", user_id)
    await db.commit()
    return [f.dump() for f in findings]


async def cancel(db: AsyncSession, r: InspectionRequest, reason: str | None, user_id: int) -> None:
    if r.status not in LIVE_REQUEST:
        raise UnprocessableEntityException(f"A {r.status.replace('_', ' ')} request isn't cancelled.")
    if r.status != RequestStatus.DRAFT and not (reason or "").strip():
        raise UnprocessableEntityException("Say why the issued request is cancelled.")
    was = r.status
    await record_transition(db, REQUEST_ENTITY, r.id, r.status, RequestStatus.CANCELLED, user_id, reason)
    r.status = RequestStatus.CANCELLED.value
    r.cancelled_reason = reason
    await db.flush()
    for lk in await links_of(db, r.id):
        i = await db.get(Inspection, lk.inspection_id)
        if i is None or i.status != InspectionStatus.REQUESTED or not lk.prior_status:
            continue
        other = await db.scalar(
            select(InspectionRequest.id)
            .join(RequestLink, RequestLink.request_id == InspectionRequest.id)
            .where(
                RequestLink.inspection_id == i.id,
                InspectionRequest.id != r.id,
                InspectionRequest.status.in_(OPEN_REQUEST),
            )
        )
        if not other:
            await record_transition(db, ENTITY, i.id, i.status, lk.prior_status, user_id, note=f"{r.code} cancelled")
            i.status = lk.prior_status
    if was != RequestStatus.DRAFT:
        await _send_callout(db, r, "cancelled", user_id)
    await db.commit()


async def history(db: AsyncSession, r: InspectionRequest) -> list[dict[str, Any]]:
    rows = await history_of(db, REQUEST_ENTITY, r.id)
    names = await user_names(db, {x["changed_by_id"] for x in rows})
    return [{**x, "changed_by_name": names.get(x["changed_by_id"]) if x["changed_by_id"] else None} for x in rows]


# --- calendar ----------------------------------------------------------------------------------------


async def calendar(
    db: AsyncSession, project_id: int, start: datetime, end: datetime, *, mine_user_id: int | None, include_drafts: bool
) -> list[dict[str, Any]]:
    where: list[Any] = [
        InspectionRequest.project_id == project_id,
        InspectionRequest.scheduled_start >= start,
        InspectionRequest.scheduled_start < end,
    ]
    if not include_drafts:
        where.append(InspectionRequest.status != RequestStatus.DRAFT)
    rows = list(
        (await db.execute(select(InspectionRequest).where(*where).order_by(InspectionRequest.scheduled_start))).scalars()
    )
    out = []
    for item in await read_requests(db, rows):
        if mine_user_id is not None:
            involved = (
                {item["requested_by_id"]}
                | {x["user_id"] for p in item["parties"] for x in p["recipients"]}
                | {p["witness_user_id"] for p in item["parties"]}
            )
            if mine_user_id not in involved:
                continue
        out.append(
            {
                "id": item["id"],
                "code": item["code"],
                "title": item["title"],
                "discipline": item["discipline"],
                "status": item["status"],
                "start": item["scheduled_start"],
                "end": item["scheduled_end"],
                "location_ref": item["location_ref"],
                "strongest_point": item["strongest_point"],
                "inspections": [i["code"] for i in item["inspections"]],
                "parties": [
                    {
                        "party": p["party"],
                        "point": p["point"],
                        "attendance": p["attendance"],
                        "notice_delivery": p["notice_delivery"],
                    }
                    for p in item["parties"]
                    if p["external_hw"]
                ],
            }
        )
    return out
