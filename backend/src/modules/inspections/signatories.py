"""Distinct-signer counting for ITP lines and the additional-signatory action.

Counting is delegated to the pure rules in ``signatory_rules``; this file reads the stored signatures, compares each
one's content digest with the record's current one and, for the action, adds one signature in the additional role.
The caller loads the record under a row lock first, so two simultaneous submissions by one person run one after the
other; stale signatures are voided before the duplicate check, and the partial unique index is the backstop."""

from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import ConflictException, UnprocessableEntityException
from . import signing
from .constants import InspectionStatus, Kind, SignatureRole
from .models import Inspection, InspectionItem, InspectionSignature
from .signatory_rules import SignatureFact, collected_count, is_met, signer_roles

SIGNABLE = (
    InspectionStatus.REQUESTED.value,
    InspectionStatus.IN_PROGRESS.value,
    InspectionStatus.SUBMITTED.value,
    InspectionStatus.RETURNED.value,
)
"""A planned line has nothing to sign yet and a passed or failed one is decided."""


def facts_from(rows: list[InspectionSignature], current_hash: str) -> list[SignatureFact]:
    return [SignatureFact(s.signer_user_id, s.role, s.status, s.content_sha256 == current_hash) for s in rows]


async def facts_of(db: AsyncSession, inspection: Inspection) -> list[SignatureFact]:
    current = await signing.content_hash(db, inspection)
    return facts_from(await signing.signatures_of(db, inspection.id), current)


def _names(rows: list[InspectionSignature]) -> dict[int, str | None]:
    names: dict[int, str | None] = {}
    for sig in rows:
        if sig.signer_user_id is not None:
            names.setdefault(sig.signer_user_id, (sig.signer_snapshot or {}).get("name"))
    return names


async def status_of(db: AsyncSession, inspection: Inspection) -> dict[str, Any]:
    """Required, collected, the distinct people with their roles, and whether the requirement is met."""
    current = await signing.content_hash(db, inspection)
    rows = await signing.signatures_of(db, inspection.id)
    facts = facts_from(rows, current)
    names = _names(rows)
    signers = [{**person, "name": names.get(person["user_id"])} for person in signer_roles(facts)]
    collected = collected_count(facts)
    required = inspection.required_signatories
    return {
        "inspection_id": inspection.id,
        "required": required,
        "collected": collected,
        "met": is_met(collected, required),
        "signers": signers,
    }


async def collected_for_lines(db: AsyncSession, lines: list[Inspection]) -> dict[int, int]:
    """Distinct signers per line for a whole instance with two set-based reads, never one read per line."""
    if not lines:
        return {}
    ids = [line.id for line in lines]
    sigs = (await db.execute(select(InspectionSignature).where(InspectionSignature.inspection_id.in_(ids)))).scalars()
    by_line: dict[int, list[InspectionSignature]] = {}
    for sig in sigs:
        by_line.setdefault(sig.inspection_id, []).append(sig)
    items = (await db.execute(select(InspectionItem).where(InspectionItem.inspection_id.in_(ids)))).scalars()
    items_by_line: dict[int, list[InspectionItem]] = {}
    for item in items:
        items_by_line.setdefault(item.inspection_id, []).append(item)
    out: dict[int, int] = {}
    for line in lines:
        rows = by_line.get(line.id, [])
        if not rows:
            out[line.id] = 0
            continue
        current = signing.sha256_of(signing.canonical(line, items_by_line.get(line.id, [])))
        out[line.id] = collected_count(facts_from(rows, current))
    return out


DUPLICATE = "You have already signed this line as an additional signatory."


async def _already_signed(db: AsyncSession, inspection: Inspection, user_id: int) -> bool:
    """A live signature of this person in the additional role. Stale ones were voided just before, so a live row
    here always covers the current content."""
    found = await db.scalar(
        select(InspectionSignature.id).where(
            InspectionSignature.inspection_id == inspection.id,
            InspectionSignature.role == SignatureRole.ADDITIONAL_SIGNATORY.value,
            InspectionSignature.signer_user_id == user_id,
            InspectionSignature.status.in_(signing.LIVE),
        )
    )
    return found is not None


SignFindings = Callable[[], Awaitable[Sequence[Any]]]
"""Answers why signing is not allowed now (the eligibility check for the sign action). The router supplies it:
eligibility reads this file for the approval finding, so importing it here would be circular."""


async def add_additional_signatory(
    db: AsyncSession,
    inspection: Inspection,
    user_id: int,
    held: frozenset[str],
    *,
    accept_intent: bool,
    sign_findings: SignFindings,
) -> InspectionSignature:
    """Add one signature in the additional role over the current content. The caller holds the row lock.

    Refused for a record that is not an ITP line, one that is planned or decided, one without a live inspector
    signature, and (as a conflict) a person who already signed in this role. Rolls back before raising."""
    try:
        if inspection.kind != Kind.ITP:
            raise UnprocessableEntityException("Only an ITP line takes additional signatories.")
        if inspection.status not in SIGNABLE:
            state = inspection.status.replace("_", " ")
            raise UnprocessableEntityException(f"This line is {state}; an additional signatory signs only while it is open.")
        await signing.void_stale(db, inspection)
        if await signing.live_signature(db, inspection, SignatureRole.INSPECTOR) is None:
            raise UnprocessableEntityException("The inspector must sign the current content first.")
        findings = [
            f
            for f in await sign_findings()
            if f.blocking and not (f.code == "NOT_EDITABLE" and inspection.status == InspectionStatus.SUBMITTED)
        ]
        if findings:
            raise UnprocessableEntityException("; ".join(f"{f.code}: {f.message}" for f in findings))
        if not accept_intent:
            raise UnprocessableEntityException("Accept the signing statement to sign (accept_intent).")
        if await _already_signed(db, inspection, user_id):
            raise ConflictException(DUPLICATE)
        snapshot, _ = await signing.competency_findings(db, user_id, inspection.required_qualification, date.today())
        sig = await signing.sign(db, inspection, SignatureRole.ADDITIONAL_SIGNATORY, user_id, held=held, competencies=snapshot)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(DUPLICATE) from exc
    except Exception:
        await db.rollback()
        raise
    return sig
