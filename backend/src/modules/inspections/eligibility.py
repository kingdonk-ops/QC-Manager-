"""Stateless checks: may this action happen on this record now, and if not, why (KERP ``eligibility`` +
``construction_control`` hold/witness evaluation, as plain functions instead of a CEL rule engine).

Every check returns findings ``{code, message, blocking}``; nothing is stored.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import (
    Attendance,
    InspectionStatus,
    RequestStatus,
    SignatureRole,
    SignatureStatus,
    WitnessStatus,
    external_hw,
    has_hold,
)
from .models import Inspection, InspectionRequest, InspectionSettings, RequestLink, RequestParty
from .signing import competency_findings, live_signature


@dataclass
class Finding:
    code: str
    message: str
    blocking: bool = True

    def dump(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "blocking": self.blocking}


ACTIONS = ("fill", "request", "sign", "submit", "approve", "hold_release")


async def settings_of(db: AsyncSession, project_id: int) -> InspectionSettings:
    s = await db.get(InspectionSettings, project_id)
    if s is None:
        s = InspectionSettings(project_id=project_id)
        db.add(s)
        await db.flush()
    return s


async def unreleased_holds_before(db: AsyncSession, inspection: Inspection) -> list[Inspection]:
    """Earlier lines of the same ITP whose Hold point isn't released: they block this line."""
    if inspection.itp_instance_id is None or inspection.itp_position is None:
        return []
    rows = await db.execute(
        select(Inspection)
        .where(
            Inspection.itp_instance_id == inspection.itp_instance_id,
            Inspection.itp_position < inspection.itp_position,
            Inspection.hold_released_at.is_(None),
        )
        .order_by(Inspection.itp_position)
    )
    return [line for line in rows.scalars() if has_hold(line.points)]


async def hold_findings(db: AsyncSession, inspection: Inspection) -> list[Finding]:
    blocked = await unreleased_holds_before(db, inspection)
    if not blocked:
        return []
    names = ", ".join(f"{b.code} {b.title}" for b in blocked[:3])
    return [Finding("HOLD_NOT_RELEASED", f"Hold point not released: {names}. Work can't proceed past it.")]


async def latest_request(db: AsyncSession, inspection_id: int) -> InspectionRequest | None:
    """The most recently issued request linking the record (cancelled ones don't count)."""
    found: InspectionRequest | None = await db.scalar(
        select(InspectionRequest)
        .join(RequestLink, RequestLink.request_id == InspectionRequest.id)
        .where(
            RequestLink.inspection_id == inspection_id,
            InspectionRequest.issued_at.is_not(None),
            InspectionRequest.status != RequestStatus.CANCELLED,
        )
        .order_by(InspectionRequest.issued_at.desc(), InspectionRequest.id.desc())
        .limit(1)
    )
    return found


def party_met(party: RequestParty, request_status: str) -> bool:
    """A party's witness requirement: attended or waived, or absent from a Witness point after valid notice."""
    if request_status == RequestStatus.FAILED:
        return False
    if party.attendance in (Attendance.ATTENDED, Attendance.WAIVED):
        return True
    return party.attendance == Attendance.ABSENT and party.point == "W" and party.notice_valid_at_outcome is True


async def witness_status(db: AsyncSession, inspection: Inspection) -> tuple[str, dict[str, str]]:
    """Overall and per external party: ``not_required | none | pending | satisfied | not_satisfied``.

    The requirement comes from the record's own points (the ITP line), never from the request's, so lowering a
    point on a request never lifts a hold."""
    needed = external_hw(inspection.points)
    if not needed:
        return WitnessStatus.NOT_REQUIRED.value, {}
    request = await latest_request(db, inspection.id)
    if request is None:
        return WitnessStatus.NONE.value, {p: WitnessStatus.NONE.value for p in needed}
    parties = {
        p.party: p for p in (await db.execute(select(RequestParty).where(RequestParty.request_id == request.id))).scalars()
    }
    per: dict[str, str] = {}
    for name in needed:
        party = parties.get(name)
        if request.status in (RequestStatus.REQUESTED, RequestStatus.CONFIRMED):
            met = party is not None and party.attendance == Attendance.WAIVED
            per[name] = WitnessStatus.SATISFIED.value if met else WitnessStatus.PENDING.value
        elif party is None:
            per[name] = WitnessStatus.NOT_SATISFIED.value
        else:
            met = party_met(party, request.status)
            per[name] = WitnessStatus.SATISFIED.value if met else WitnessStatus.NOT_SATISFIED.value
    values = set(per.values())
    if values == {WitnessStatus.SATISFIED.value}:
        overall = WitnessStatus.SATISFIED.value
    elif WitnessStatus.NOT_SATISFIED.value in values:
        overall = WitnessStatus.NOT_SATISFIED.value
    else:
        overall = WitnessStatus.PENDING.value
    return overall, per


async def witness_findings(db: AsyncSession, inspection: Inspection) -> list[Finding]:
    overall, per = await witness_status(db, inspection)
    if overall in (WitnessStatus.NOT_REQUIRED, WitnessStatus.SATISFIED):
        return []
    unmet = [p for p, s in per.items() if s != WitnessStatus.SATISFIED]
    who = ", ".join(f"{p.replace('_', ' ')} ({inspection.points.get(p)})" for p in unmet)
    if overall == WitnessStatus.NONE:
        return [Finding("RFI_REQUIRED", f"Raise an inspection request first: {who} must be called out.")]
    if overall == WitnessStatus.PENDING:
        return [Finding("WITNESS_PENDING", f"The call-out is still open for {who}.")]
    return [Finding("WITNESS_NOT_SATISFIED", f"The witness requirement was not met for {who}: reschedule the request.")]


async def check(
    db: AsyncSession,
    inspection: Inspection,
    action: str,
    *,
    user_id: int | None = None,
    on: date | None = None,
) -> list[Finding]:
    """Why ``action`` can't happen now (empty list: it can)."""
    on = on or date.today()
    out: list[Finding] = []
    if action in ("fill", "request", "sign", "submit"):
        out += await hold_findings(db, inspection)
    if action in ("fill", "sign", "submit") and inspection.status not in (
        InspectionStatus.PLANNED,
        InspectionStatus.REQUESTED,
        InspectionStatus.IN_PROGRESS,
        InspectionStatus.RETURNED,
    ):
        out.append(Finding("NOT_EDITABLE", f"The record is {inspection.status.replace('_', ' ')}."))
    if action == "request" and inspection.status != InspectionStatus.PLANNED:
        out.append(Finding("NOT_REQUESTABLE", "Only a planned record can be called out."))
    if action == "submit":
        if not inspection.is_formal:
            out.append(Finding("INFORMAL", "An informal record is completed directly; it has no review."))
        out += await witness_findings(db, inspection)
        if inspection.requires_client_signature and not await live_signature(db, inspection, SignatureRole.CLIENT):
            out.append(Finding("CLIENT_SIGNATURE_MISSING", "This template needs the client's co-signature before submit."))
    if action in ("sign", "submit", "hold_release") and user_id is not None:
        _, problems = await competency_findings(db, user_id, inspection.required_qualification, on)
        out += [Finding(code, message) for code, message in problems]
    if action == "approve":
        if inspection.status != InspectionStatus.SUBMITTED:
            out.append(Finding("NOT_SUBMITTED", "Only a submitted record can be reviewed."))
        if inspection.requires_client_signature:
            sig = await live_signature(db, inspection, SignatureRole.CLIENT)
            if sig is None:
                out.append(Finding("CLIENT_SIGNATURE_MISSING", "The client's co-signature is missing."))
            elif sig.status == SignatureStatus.PROVISIONAL:
                out.append(Finding("CLIENT_SIGNATURE_PROVISIONAL", "The client hasn't confirmed their co-signature yet."))
        if user_id is not None and user_id in (inspection.inspector_id, inspection.submitted_by_id):
            allowed = (await settings_of(db, inspection.project_id)).allow_self_approval
            if not allowed:
                out.append(Finding("SELF_APPROVAL", "Nobody approves an inspection they performed or submitted."))
    if action == "hold_release":
        if not has_hold(inspection.points):
            out.append(Finding("NO_HOLD_POINT", "This line has no Hold point."))
        elif inspection.hold_released_at is not None:
            out.append(Finding("ALREADY_RELEASED", "The hold is already released."))
        if inspection.status not in (InspectionStatus.COMPLETED, InspectionStatus.CLOSED) or inspection.result != "pass":
            out.append(Finding("LINE_NOT_ACCEPTED", "Release a hold only once its inspection is accepted."))
        out += await witness_findings(db, inspection)
        out += await hold_findings(db, inspection)
    return out


async def unsigned_hold_points(db: AsyncSession, project_id: int, node_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """ITP lines with a Hold point not yet released, within a dossier scope (all of the project when ``node_ids`` is None).

    The MDR gate calls this: a dossier can't be issued past an unreleased Hold point.
    """
    query = select(Inspection).where(
        Inspection.project_id == project_id,
        Inspection.kind == "itp",
        Inspection.hold_released_at.is_(None),
        Inspection.status != "void",
    )
    if node_ids is not None:
        query = query.where(Inspection.node_id.in_(node_ids))
    rows = (await db.execute(query.order_by(Inspection.code))).scalars()
    return [
        {"reference": line.code, "message": f"Hold point not released: {line.title}", "link": f"/inspections/{line.id}"}
        for line in rows
        if has_hold(line.points)
    ]
