"""As-built records: create, edit, delete, survey, verify and sign.

A survey, a verification and a signature are written to the audit ledger in the same transaction as the change, and a
step that fails part-way is rolled back whole before the error is raised. Verifying an out-of-tolerance record raises
a workmanship report in that same transaction (when the issues module is on for the project), so a report that cannot
be created fails the verification; the raised event is published only after the commit."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.http_exceptions import ConflictException, UnprocessableEntityException
from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import NumberingError, link_allocation, next_number
from ..asset_tree import service as tree
from ..common.exceptions import ResourceNotFoundError
from ..inspections import ncr_text
from ..inspections.constants import ToleranceResult
from ..inspections.criteria import CriterionNotFoundError, get_criterion
from ..inspections.models import AcceptanceCriterion
from ..inspections.tolerance import criterion_clause
from ..ncr.auto import raise_automatic
from ..ncr.constants import Severity
from ..ncr.models import Ncr
from ..ncr.service import publish_raised
from . import rules
from .constants import AsBuiltStatus
from .models import AsBuiltRecord

ENTITY = "as_built"
NUMBER_KIND = "as_built"
SURVEY_FIELDS = ("measured_value", "deviation_value", "accuracy_value", "accuracy_unit", "surveyed_on", "notes")
LINK_FIELDS = ("criterion_id", "node_id", "item_id")


class AsBuiltNotFoundError(ResourceNotFoundError):
    public_detail = "As-built record not found."


def plain(values: dict[str, Any]) -> dict[str, Any]:
    """Request values with enumerations as their stored text."""
    return {k: v.value if isinstance(v, Enum) else v for k, v in values.items()}


async def get_record(db: AsyncSession, record_id: int) -> AsBuiltRecord:
    record = await db.get(AsBuiltRecord, record_id)
    if record is None:
        raise AsBuiltNotFoundError("No such as-built record")
    return record


async def _criterion_of(db: AsyncSession, record: AsBuiltRecord) -> AcceptanceCriterion | None:
    return await db.get(AcceptanceCriterion, record.criterion_id) if record.criterion_id is not None else None


async def check_links(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    """The criterion, node and item must belong to the project; foreign or missing ones answer not-found, and so does
    a criterion when the inspections module is switched off for the project."""
    if values.get("criterion_id") is not None:
        if not await is_enabled(db, "inspections", project_id):
            raise CriterionNotFoundError("No such criterion")
        await get_criterion(db, values["criterion_id"], project_id)
    if values.get("node_id") is not None:
        await tree.get_node(db, values["node_id"], project_id)
    if values.get("item_id") is not None:
        await tree.get_item(db, values["item_id"], project_id)


# --- create, edit, delete ----------------------------------------------------------------------------


async def create_record(db: AsyncSession, values: dict[str, Any], user_id: int) -> AsBuiltRecord:
    values = plain(values)
    project_id = values["project_id"]
    await check_links(db, project_id, values)
    try:
        number = await next_number(db, NUMBER_KIND, project_id, fallback_prefix="ASB", user_id=user_id)
        record = AsBuiltRecord(number=number, created_by_id=user_id, **values)
        db.add(record)
        await db.flush()
        await link_allocation(db, project_id, NUMBER_KIND, number, (ENTITY, record.id))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if isinstance(exc, NumberingError):
            raise UnprocessableEntityException("; ".join(exc.problems)) from exc
        raise
    return record


async def update_record(db: AsyncSession, record: AsBuiltRecord, changes: dict[str, Any], user_id: int) -> AsBuiltRecord:
    """An ordinary edit. The rules decide what is refused (see ``rules.edit_refusal``); a draft whose measured value or
    criterion changes goes back to not assessed, since nothing has been judged yet."""
    changes = plain(changes)
    refusal = rules.edit_refusal(record.status, changes, {k: getattr(record, k) for k in changes})
    if refusal is not None:
        raise (ConflictException if refusal.kind == rules.CONFLICT else UnprocessableEntityException)(refusal.message)
    await check_links(db, record.project_id, {k: v for k, v in changes.items() if k in LINK_FIELDS})
    before = record.status
    try:
        for key, value in changes.items():
            setattr(record, key, value)
        if record.status == AsBuiltStatus.DRAFT and ("measured_value" in changes or "criterion_id" in changes):
            record.tolerance_result = ToleranceResult.NOT_ASSESSED.value
        if record.status != before:
            await record_audit(
                db,
                f"as_built.record.{record.status}",
                ENTITY,
                record.id,
                actor_id=user_id,
                project_id=record.project_id,
                summary=f"{record.number} {record.status}",
                before={"status": before},
                after={"status": record.status},
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return record


async def delete_record(db: AsyncSession, record: AsBuiltRecord) -> None:
    error = rules.deletion_error(record.status)
    if error is not None:
        raise ConflictException(error)
    await db.delete(record)
    await db.commit()


# --- survey, verify, sign ----------------------------------------------------------------------------


async def survey_record(db: AsyncSession, record: AsBuiltRecord, values: dict[str, Any], user_id: int) -> AsBuiltRecord:
    """Record a survey while the record is draft or surveyed: store what was given, judge the measured value (the given
    one, else the stored one) against the criterion and keep the tolerance result. Nothing is raised at this step."""
    error = rules.survey_error(record.status)
    if error is not None:
        raise UnprocessableEntityException(error)
    criterion = await _criterion_of(db, record)
    before = {"status": record.status, "tolerance_result": record.tolerance_result}
    try:
        for key in SURVEY_FIELDS:
            if values.get(key) is not None:
                setattr(record, key, values[key])
        record.tolerance_result = rules.tolerance_result(criterion, record.measured_value)
        record.surveyed_by_id = record.surveyed_by_id or user_id
        record.status = AsBuiltStatus.SURVEYED.value
        await record_audit(
            db,
            "as_built.record.surveyed",
            ENTITY,
            record.id,
            actor_id=user_id,
            project_id=record.project_id,
            summary=f"{record.number} surveyed: {record.tolerance_result}",
            before=before,
            after={"status": record.status, "tolerance_result": record.tolerance_result},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return record


async def verify_record(
    db: AsyncSession, record: AsBuiltRecord, *, user_id: int, notes: str | None, severity: Severity | None
) -> AsBuiltRecord:
    """Verify a surveyed record. Out of tolerance raises a workmanship report (default major) and stores its
    identifier; within and not assessed raise nothing. The legal-record flag is not touched."""
    error = rules.verify_error(record.status)
    if error is not None:
        raise UnprocessableEntityException(error)
    report: Ncr | None = None
    try:
        record.status = AsBuiltStatus.VERIFIED.value
        if notes is not None:
            record.verifier_notes = notes
        if record.tolerance_result == ToleranceResult.OUT_OF_TOLERANCE and await is_enabled(db, "ncr", record.project_id):
            report = await _raise_report(db, record, severity, user_id)
            record.report_id = report.id
        await record_audit(
            db,
            "as_built.record.verified",
            ENTITY,
            record.id,
            actor_id=user_id,
            project_id=record.project_id,
            summary=f"{record.number} verified: {record.tolerance_result}",
            before={"status": AsBuiltStatus.SURVEYED.value},
            after={"status": record.status, "tolerance_result": record.tolerance_result, "report_id": record.report_id},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    if report is not None:
        await publish_raised(report)
    return record


async def _raise_report(db: AsyncSession, record: AsBuiltRecord, severity: Severity | None, user_id: int) -> Ncr:
    """The workmanship report, created without committing."""
    criterion = await _criterion_of(db, record)
    return await raise_automatic(
        db,
        project_id=record.project_id,
        title=ncr_text.event_title("as_built_out_of_tolerance", record.number, record.title),
        description=ncr_text.description(
            source_label="as-built record",
            number=record.number,
            record_description=record.title,
            context=rules.report_lines(record, record.verifier_notes),
            clause=criterion_clause(criterion, record.measured_value) if criterion else None,
        ),
        raised_by_id=user_id,
        severity=severity.value if severity else ncr_text.default_severity("fail"),
        source="as_built",
        source_reference=record.number,
        location=record.location,
        trade=record.discipline,
        source_data=ncr_text.source_data(
            source_kind="as_built_record",
            record_id=record.id,
            number=record.number,
            outcome=ToleranceResult.OUT_OF_TOLERANCE.value,
            criterion_id=record.criterion_id,
            measured_value=record.measured_value,
            report_kind="workmanship",
            capture_method=record.capture_method,
            instrument=record.instrument,
            accuracy_class=record.accuracy_class,
            deviation_value=record.deviation_value,
        ),
    )


async def sign_record(
    db: AsyncSession,
    record: AsBuiltRecord,
    *,
    user_id: int,
    valid: bool,
    notes: str | None,
    signed_at: datetime | None,
    ip: str | None,
) -> AsBuiltRecord:
    """Sign the legal-record attestation of a verified record. Valid sets the flag and moves the record to recorded;
    not valid stores the same signature data and leaves the flag false and the record verified."""
    error = rules.sign_error(record.status)
    if error is not None:
        raise UnprocessableEntityException(error)
    digest = rules.attestation_digest(rules.attestation_snapshot(record, valid=valid, signer_id=user_id))
    try:
        record.signed_by_id = user_id
        record.signed_at = signed_at or datetime.now(UTC)
        record.signed_ip = ip
        record.signed_digest = digest
        record.signature_notes = notes
        if valid:
            record.legal_record = True
            record.status = AsBuiltStatus.RECORDED.value
        await record_audit(
            db,
            "as_built.record.signed",
            ENTITY,
            record.id,
            actor_id=user_id,
            project_id=record.project_id,
            summary=f"{record.number} signed as {'valid' if valid else 'not valid'}",
            before={"status": AsBuiltStatus.VERIFIED.value},
            after={"status": record.status, "valid": valid, "digest": digest},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return record
