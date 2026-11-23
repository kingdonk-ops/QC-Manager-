"""Pure as-built rules: the status flow for survey, verify, sign and ordinary edits, the tolerance result, the
attestation snapshot with its SHA-256 digest, and the context lines of the workmanship report.

The tolerance result reuses the inspections tolerance rules, and the digest uses the destination's canonical JSON
hashing helper (the one inspection signatures use), so it does not depend on key order. This file otherwise imports
neither the web framework nor the database layer."""

from collections.abc import Mapping
from typing import Any, NamedTuple

from ..inspections.signing import sha256_of
from ..inspections.tolerance import judge_criterion
from .constants import ACTION_FOR, DELETABLE, EDIT_MOVES, FLOW, JUDGED, KEPT, LOCKED, SURVEYABLE, AsBuiltStatus

CLIENT_ERROR = "client_error"
CONFLICT = "conflict"
JUDGED_FIELDS = ("measured_value", "criterion_id")


class Refusal(NamedTuple):
    """Why an ordinary edit is refused: a client error or a conflict, with the explanation."""

    kind: str
    message: str


def tolerance_result(criterion: Any | None, measured: Any) -> str:
    """Within, out of tolerance or not assessed. No criterion, a free-text or boolean rule, a missing limit or a value
    that is not a plain decimal is never read as conforming."""
    return judge_criterion(criterion, measured).value


# --- the actions -------------------------------------------------------------------------------------


def survey_error(status: str) -> str | None:
    """A survey is recorded while the record is draft or surveyed, so it can be repeated."""
    if status in SURVEYABLE:
        return None
    return f"This record is {status}, so a survey cannot be recorded; a survey needs a draft or surveyed record."


def verify_error(status: str) -> str | None:
    if status == AsBuiltStatus.SURVEYED:
        return None
    hint = " Record a survey first." if status == AsBuiltStatus.DRAFT else ""
    return f"This record is {status}, so it cannot be verified; verify needs a surveyed record.{hint}"


def sign_error(status: str) -> str | None:
    if status == AsBuiltStatus.VERIFIED:
        return None
    hint = " Verify it first." if status in (AsBuiltStatus.DRAFT, AsBuiltStatus.SURVEYED) else ""
    return f"This record is {status}, so it cannot be signed; the attestation needs a verified record.{hint}"


def allowed_transitions(status: str) -> set[str]:
    """Every status a record can move to from ``status``, by an action or by an ordinary edit."""
    return set(FLOW.get(status, set()))


# --- ordinary edits ----------------------------------------------------------------------------------


def _changed(changes: Mapping[str, Any], stored: Mapping[str, Any], key: str) -> bool:
    return key in changes and changes[key] != stored.get(key)


def edit_refusal(current: str, changes: Mapping[str, Any], stored: Mapping[str, Any]) -> Refusal | None:
    """Whether an ordinary edit may be applied to a record in ``current`` status.

    Recorded and void records cannot be edited at all. An edit never sets surveyed, verified or recorded (the survey,
    verify and sign actions do), and moves only draft or surveyed to void and verified to superseded. Once a survey
    has been recorded the measured value and criterion change only by a new survey; a verified or superseded record
    is never rewritten. Only real changes count, so re-sending a stored value is not a change."""
    if current in LOCKED:
        return Refusal(CLIENT_ERROR, f"A {current} record cannot be edited.")
    target = changes.get("status")
    if target is not None and target != current:
        action = ACTION_FOR.get(target)
        if action:
            return Refusal(CONFLICT, f"The status {target} is reached through the {action} action, not by an edit.")
        if (current, target) not in EDIT_MOVES:
            return Refusal(CLIENT_ERROR, f"An edit cannot move a {current} record to {target}.")
    if current in KEPT and any(k != "status" and _changed(changes, stored, k) for k in changes):
        return Refusal(
            CONFLICT, f"A {current} record is never rewritten. Supersede it and create a new record for the correction."
        )
    if current in JUDGED and any(_changed(changes, stored, k) for k in JUDGED_FIELDS):
        return Refusal(
            CONFLICT,
            "The measured value and criterion change only by recording a new survey while the record is surveyed; "
            "use the survey action.",
        )
    return None


def deletion_error(status: str) -> str | None:
    """Verified and later records are never deleted; they are superseded and corrected by a new record."""
    if status in DELETABLE:
        return None
    return f"A {status} record is evidence and is never deleted. Supersede it and create a new record instead."


# --- the attestation ---------------------------------------------------------------------------------


def attestation_snapshot(record: Any, *, valid: bool, signer_id: int) -> dict[str, Any]:
    """What the attestation digest covers: the record's identity, capture, accuracy, criterion, measured value and
    tolerance result, the validity decision and the signer. Status and notes are left out."""
    surveyed_on = record.surveyed_on.isoformat() if record.surveyed_on else None
    return {
        "id": record.id,
        "number": record.number,
        "title": record.title,
        "capture": [
            record.capture_method,
            record.instrument,
            record.calibration_ref,
            record.coordinate_system,
            surveyed_on,
            record.surveyed_by_id,
        ],
        "accuracy": [record.accuracy_class, record.accuracy_value, record.accuracy_unit],
        "criterion_id": record.criterion_id,
        "measured_value": record.measured_value,
        "tolerance_result": record.tolerance_result,
        "valid": valid,
        "signer_id": signer_id,
    }


def attestation_digest(snapshot: dict[str, Any]) -> str:
    """64 hexadecimal characters; the same content gives the same digest whatever the key order."""
    return sha256_of(snapshot)


# --- the report --------------------------------------------------------------------------------------


def report_lines(record: Any, verifier_notes: str | None = None) -> list[str]:
    """Context lines of the workmanship report: capture method, instrument, accuracy class and value, the deviation
    value and the verifier's notes. The criterion clause is added by the caller."""
    lines = [f"Capture method: {record.capture_method.replace('_', ' ')}."]
    if record.instrument:
        lines.append(f"Instrument: {record.instrument}.")
    accuracy = f"Accuracy class: {record.accuracy_class}"
    if record.accuracy_value:
        accuracy += f", value {record.accuracy_value}" + (f" {record.accuracy_unit}" if record.accuracy_unit else "")
    lines.append(accuracy + ".")
    if record.deviation_value:
        lines.append(f"Deviation value: {record.deviation_value}.")
    if verifier_notes and verifier_notes.strip():
        lines.append(f"Verifier notes: {verifier_notes.strip()}")
    return lines
