"""Signing attestation, client co-sign, competency at signing and delegation of authority (KERP TD-219,
TD-433, TD-434, TD-591, TD-592), on QC Manager's session auth.

A signature stores who signed (a snapshot that never changes later), in which role, the statement they
accepted, the competencies checked at that instant and the SHA-256 of the record's canonical content. A later
change of the record voids every signature over the old content.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import ConflictException, ForbiddenException, UnprocessableEntityException
from ..user.models import User
from .constants import (
    INTENT,
    INTENT_VERSION,
    MAX_DELEGATION_DAYS,
    SignatureRole,
    SignatureStatus,
)
from .models import Competency, Delegation, Inspection, InspectionItem, InspectionSignature

LIVE = (SignatureStatus.VALID.value, SignatureStatus.PROVISIONAL.value)


def now() -> datetime:
    return datetime.now(UTC)


# --- content hash ------------------------------------------------------------------------------------


def canonical(inspection: Inspection, items: list[InspectionItem]) -> dict[str, Any]:
    """What a signature covers: the header, the anchor and every answer. Status and review bookkeeping are left out."""
    return {
        "id": inspection.id,
        "code": inspection.code,
        "kind": inspection.kind,
        "title": inspection.title,
        "template": [inspection.template_id, inspection.template_version],
        "anchor": [inspection.node_id, inspection.item_id],
        "location": [inspection.location, inspection.area, inspection.location_node_id],
        "trade": inspection.trade,
        "inspector_id": inspection.inspector_id,
        "inspected_date": inspection.inspected_date.isoformat() if inspection.inspected_date else None,
        "notes": inspection.notes,
        "points": inspection.points or {},
        "acceptance_criteria": inspection.acceptance_criteria,
        "items": [[i.id, i.text, i.result, i.reading, i.notes] for i in sorted(items, key=lambda i: i.position)],
    }


def sha256_of(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


async def content_hash(db: AsyncSession, inspection: Inspection) -> str:
    items = list((await db.execute(select(InspectionItem).where(InspectionItem.inspection_id == inspection.id))).scalars())
    return sha256_of(canonical(inspection, items))


async def signatures_of(db: AsyncSession, inspection_id: int) -> list[InspectionSignature]:
    rows = await db.execute(
        select(InspectionSignature)
        .where(InspectionSignature.inspection_id == inspection_id)
        .order_by(InspectionSignature.signed_at, InspectionSignature.id)
    )
    return list(rows.scalars())


async def void_stale(db: AsyncSession, inspection: Inspection, reason: str = "The record changed after signing") -> int:
    """Void every live signature over content that is no longer the record's. Returns how many."""
    current = await content_hash(db, inspection)
    voided = 0
    for sig in await signatures_of(db, inspection.id):
        if sig.status in LIVE and sig.content_sha256 != current:
            sig.status = SignatureStatus.VOID.value
            sig.voided_at = now()
            sig.void_reason = reason
            voided += 1
            if sig.role == SignatureRole.HOLD_RELEASE:
                inspection.hold_released_at = None
                inspection.hold_released_by_id = None
    return voided


async def live_signature(
    db: AsyncSession, inspection: Inspection, role: SignatureRole, *, statuses: tuple[str, ...] = LIVE
) -> InspectionSignature | None:
    current = await content_hash(db, inspection)
    for sig in reversed(await signatures_of(db, inspection.id)):
        if sig.role == role and sig.status in statuses and sig.content_sha256 == current:
            return sig
    return None


# --- competency --------------------------------------------------------------------------------------


def competency_valid(c: Competency, on: date) -> bool:
    return (c.issued_on is None or c.issued_on <= on) and (c.expires_on is None or c.expires_on >= on)


def competency_snapshot(c: Competency, on: date) -> dict[str, Any]:
    return {
        "id": c.id,
        "qualification": c.qualification,
        "level": c.level,
        "number": c.number,
        "issuer": c.issuer,
        "issued_on": c.issued_on.isoformat() if c.issued_on else None,
        "expires_on": c.expires_on.isoformat() if c.expires_on else None,
        "verified": c.verified,
        "valid_at_signing": competency_valid(c, on),
    }


async def competencies_of(db: AsyncSession, user_id: int) -> list[Competency]:
    rows = await db.execute(select(Competency).where(Competency.user_id == user_id).order_by(Competency.qualification))
    return list(rows.scalars())


async def competency_findings(
    db: AsyncSession, user_id: int, required: str | None, on: date
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """The snapshot of the signer's competencies and, when a qualification is required, why they can't sign."""
    held = await competencies_of(db, user_id)
    snapshot = [competency_snapshot(c, on) for c in held]
    if not required:
        return snapshot, []
    matching = [c for c in held if c.qualification.strip().lower() == required.strip().lower()]
    if any(competency_valid(c, on) for c in matching):
        return snapshot, []
    if matching:
        latest = max((c.expires_on for c in matching if c.expires_on), default=None)
        when = f" (expired {latest.isoformat()})" if latest else ""
        return snapshot, [("COMPETENCY_EXPIRED", f"Your {required} competency is not valid on {on.isoformat()}{when}.")]
    return snapshot, [("COMPETENCY_MISSING", f"Signing needs a current {required} competency in the register.")]


# --- delegation --------------------------------------------------------------------------------------


async def active_delegation(
    db: AsyncSession, project_id: int, delegator_id: int, kind: str, at: datetime | None = None
) -> Delegation | None:
    at = at or now()
    found: Delegation | None = await db.scalar(
        select(Delegation).where(
            Delegation.project_id == project_id,
            Delegation.delegator_id == delegator_id,
            Delegation.kind == kind,
            Delegation.revoked_at.is_(None),
            Delegation.starts_at <= at,
            Delegation.ends_at > at,
        )
    )
    return found


async def delegates_of(db: AsyncSession, project_id: int, user_ids: set[int], kind: str) -> dict[int, Delegation]:
    """delegator id → active delegation. Never chained: a delegate's own delegations are not followed."""
    out = {}
    for uid in user_ids:
        d = await active_delegation(db, project_id, uid, kind)
        if d:
            out[uid] = d
    return out


async def create_delegation(db: AsyncSession, project_id: int, values: dict[str, Any], actor_id: int) -> Delegation:
    delegator, delegate = values["delegator_id"], values["delegate_id"]
    if delegator == delegate:
        raise UnprocessableEntityException("Nobody delegates to themself.")
    starts = values.get("starts_at") or now()
    ends = values["ends_at"]
    if ends <= starts:
        raise UnprocessableEntityException("The delegation must end after it starts.")
    if ends - starts > timedelta(days=MAX_DELEGATION_DAYS):
        raise UnprocessableEntityException(f"A delegation lasts at most {MAX_DELEGATION_DAYS} days.")
    clash = await db.scalar(
        select(Delegation.id).where(
            Delegation.project_id == project_id,
            Delegation.delegator_id == delegator,
            Delegation.kind == values["kind"],
            Delegation.revoked_at.is_(None),
            Delegation.starts_at < ends,
            Delegation.ends_at > starts,
        )
    )
    if clash:
        raise ConflictException("There is already an active delegation for this person and kind in that window.")
    d = Delegation(
        project_id=project_id,
        delegator_id=delegator,
        delegate_id=delegate,
        kind=str(values["kind"]),
        starts_at=starts,
        ends_at=ends,
        reason=values.get("reason"),
        created_by_id=actor_id,
    )
    db.add(d)
    await db.flush()
    return d


async def on_behalf(db: AsyncSession, project_id: int, actor_id: int, principal_id: int | None, kind: str) -> Delegation | None:
    """Check an "on behalf of" claim. The delegation adds no authority; the caller's own permissions still apply."""
    if principal_id is None or principal_id == actor_id:
        return None
    d = await active_delegation(db, project_id, principal_id, kind)
    if d is None or d.delegate_id != actor_id:
        raise ForbiddenException("You have no active delegation from that person for this.")
    return d


# --- signatures --------------------------------------------------------------------------------------


async def signer_snapshot(db: AsyncSession, user_id: int, role: str, held: frozenset[str] | None = None) -> dict[str, Any]:
    user = await db.get(User, user_id)
    return {
        "user_id": user_id,
        "name": user.name if user else None,
        "email": user.email if user else None,
        "role": role,
        "permissions": sorted(p for p in (held or frozenset()) if p.startswith("inspections.")),
    }


def intent_text(role: SignatureRole, name: str | None, code: str) -> str:
    return INTENT[role].format(name=name or "-", code=code)


async def sign(
    db: AsyncSession,
    inspection: Inspection,
    role: SignatureRole,
    signer_id: int,
    *,
    held: frozenset[str] | None = None,
    status: SignatureStatus = SignatureStatus.VALID,
    competencies: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> InspectionSignature:
    snapshot = await signer_snapshot(db, signer_id, role.value, held)
    sig = InspectionSignature(
        inspection_id=inspection.id,
        role=role.value,
        status=status.value,
        signer_user_id=signer_id,
        signer_snapshot=snapshot,
        content_sha256=await content_hash(db, inspection),
        signed_at=now(),
        competency_snapshot=competencies or [],
        intent_text=intent_text(role, snapshot["name"], inspection.code),
        intent_version=INTENT_VERSION,
        review_round=inspection.review_round,
        **extra,
    )
    db.add(sig)
    await db.flush()
    return sig


async def pending_cosigns_for(db: AsyncSession, user_id: int) -> list[InspectionSignature]:
    rows = await db.execute(
        select(InspectionSignature).where(
            InspectionSignature.role == SignatureRole.CLIENT,
            InspectionSignature.status == SignatureStatus.PROVISIONAL,
            InspectionSignature.signer_user_id == user_id,
        )
    )
    return list(rows.scalars())


def user_filter(user_id: int) -> Any:
    return or_(Delegation.delegator_id == user_id, Delegation.delegate_id == user_id)
