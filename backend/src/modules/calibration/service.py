"""Equipment, certificates, the calibration gate and due reminders.

``assert_calibrated(db, equipment_ids, on_date)`` is the gate other modules call before they store a
reading taken with an instrument (see the package docstring).
"""

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from .constants import ENTITY, FLOW, DisplayStatus, EquipmentStatus
from .models import CalibrationCertificate, Equipment
from .schemas import EquipmentRead


class EquipmentNotFound(ResourceNotFoundError):
    public_detail = "Equipment not found."


class DuplicateEquipmentCode(ResourceExistsError):
    public_detail = "Another piece of equipment on this project already uses that number."


class CalibrationRuleError(ValidationError):
    public_detail = "That breaks a calibration rule."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class CalibrationGateError(CalibrationRuleError):
    """Raised (422) when a reading would be taken with equipment that isn't calibrated on the day."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Calibration gate: " + "; ".join(problems) + ".")


def link_of(equipment: Equipment) -> str:
    return f"/calibration?project={equipment.project_id}&id={equipment.id}"


async def user_names(db: AsyncSession, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())


# --- status ------------------------------------------------------------------------------------------


def display_status(e: Equipment, today: date | None = None) -> str:
    today = today or date.today()
    if e.status != EquipmentStatus.IN_SERVICE:
        return e.status
    if not e.requires_calibration:
        return DisplayStatus.IN_SERVICE
    if e.due_on is None or e.due_on < today:
        return DisplayStatus.OVERDUE
    if e.due_on <= today + timedelta(days=e.reminder_days):
        return DisplayStatus.DUE
    return DisplayStatus.IN_SERVICE


def problem_on(e: Equipment, on_date: date) -> str | None:
    """Why this equipment can't be used for a reading on ``on_date``, or ``None``."""
    label = f"{e.code} ({e.name}{', SN ' + e.serial_number if e.serial_number else ''})"
    if e.status != EquipmentStatus.IN_SERVICE:
        return f"{label} is {e.status.replace('_', ' ')}"
    if not e.requires_calibration:
        return None
    if e.due_on is None:
        return f"{label} has no calibration certificate"
    if e.due_on < on_date:
        return f"{label} calibration expired {e.due_on.isoformat()}"
    if e.last_calibrated_on and e.last_calibrated_on > on_date:
        return f"{label} was not calibrated until {e.last_calibrated_on.isoformat()}"
    return None


async def assert_calibrated(
    db: AsyncSession, equipment_ids: Iterable[int], on_date: date | None = None, *, project_id: int | None = None
) -> list[Equipment]:
    """The hard gate: every piece is in service and (when it needs calibration) calibrated on ``on_date``.

    Raises ``CalibrationGateError`` (422) naming each overdue, quarantined or unknown piece. With
    ``project_id`` the equipment must also belong to that project. Returns the equipment, in order.
    """
    on_date = on_date or date.today()
    ids = list(dict.fromkeys(int(i) for i in equipment_ids))
    if not ids:
        return []
    rows = {e.id: e for e in (await db.execute(select(Equipment).where(Equipment.id.in_(ids)))).scalars()}
    problems: list[str] = []
    for i in ids:
        e = rows.get(i)
        if e is None or (project_id is not None and e.project_id != project_id):
            problems.append(f"equipment {i} is not on this project's register")
            continue
        problem = problem_on(e, on_date)
        if problem:
            problems.append(problem)
    if problems:
        raise CalibrationGateError(problems)
    return [rows[i] for i in ids]


# --- reading -----------------------------------------------------------------------------------------


async def get_equipment(db: AsyncSession, equipment_id: int) -> Equipment:
    e = await db.get(Equipment, equipment_id)
    if e is None:
        raise EquipmentNotFound(str(equipment_id))
    return e


async def read_equipment(db: AsyncSession, rows: list[Equipment]) -> list[dict[str, Any]]:
    names = await user_names(db, (e.custodian_id for e in rows))
    today = date.today()
    return [
        EquipmentRead.model_validate(e)
        .model_copy(
            update={
                "custodian_name": names.get(e.custodian_id) if e.custodian_id else None,
                "stored_status": e.status,
                "status": display_status(e, today),
                "days_to_due": (e.due_on - today).days if e.due_on else None,
                "usable": problem_on(e, today) is None,
            }
        )
        .model_dump(mode="json")
        for e in rows
    ]


# --- writing -----------------------------------------------------------------------------------------


async def _check_code(db: AsyncSession, project_id: int, code: str, own_id: int | None = None) -> None:
    clash = await db.scalar(
        select(Equipment.id).where(Equipment.project_id == project_id, Equipment.code == code, Equipment.id != (own_id or 0))
    )
    if clash:
        raise DuplicateEquipmentCode(code)


async def create_equipment(db: AsyncSession, values: dict[str, Any], user_id: int) -> Equipment:
    project_id = values["project_id"]
    code = values.pop("code", None) or await next_reference(db, "EQ", project_id)
    await _check_code(db, project_id, code)
    e = Equipment(code=code, created_by_id=user_id, **values)
    db.add(e)
    await db.flush()
    await record_transition(db, ENTITY, e.id, None, e.status, user_id, "Registered")
    return e


async def update_equipment(db: AsyncSession, e: Equipment, changes: dict[str, Any]) -> None:
    if changes.get("code") and changes["code"] != e.code:
        await _check_code(db, e.project_id, changes["code"], e.id)
    for key, value in changes.items():
        if key == "code" and not value:
            continue
        setattr(e, key, value)
    await db.flush()


async def change_status(db: AsyncSession, e: Equipment, target: str, note: str | None, user_id: int) -> None:
    if target == e.status:
        return
    assert_transition(FLOW, e.status, target)
    if target == EquipmentStatus.IN_SERVICE and e.requires_calibration:
        # The activation gate: back into service only with a current certificate.
        if e.due_on is None or e.due_on < date.today():
            raise CalibrationRuleError(f"{e.code} needs a current calibration certificate before it goes into service.")
    await record_transition(db, ENTITY, e.id, e.status, target, user_id, note)
    e.status = target
    await db.flush()


async def _check_file(db: AsyncSession, file_id: int | None, project_id: int) -> None:
    if file_id is None:
        return
    f = await db.get(StoredFile, file_id)
    if f is None or (f.project_id is not None and f.project_id != project_id):
        raise CalibrationRuleError("That certificate file isn't in this project's files.")


async def add_certificate(db: AsyncSession, e: Equipment, values: dict[str, Any], user_id: int) -> CalibrationCertificate:
    """Record a calibration: it supersedes the active certificate and moves the due date.

    Equipment that was out of service or away for calibration goes back into service; quarantined
    equipment stays quarantined until someone releases it.
    """
    await _check_file(db, values.get("file_id"), e.project_id)
    calibrated_on: date = values["calibrated_on"]
    expires_on: date = values.get("expires_on") or calibrated_on + timedelta(days=e.interval_days)
    if expires_on <= calibrated_on:
        raise CalibrationRuleError("The certificate must expire after the calibration date.")
    if calibrated_on > date.today():
        raise CalibrationRuleError("The calibration date can't be in the future.")
    await db.execute(
        update(CalibrationCertificate)
        .where(CalibrationCertificate.equipment_id == e.id, CalibrationCertificate.is_active.is_(True))
        .values(is_active=False)
    )
    cert = CalibrationCertificate(
        equipment_id=e.id,
        certificate_number=values["certificate_number"],
        calibrated_on=calibrated_on,
        expires_on=expires_on,
        facility=values.get("facility"),
        file_id=values.get("file_id"),
        result=str(values.get("result") or "pass"),
        notes=values.get("notes"),
        recorded_by_id=user_id,
    )
    db.add(cert)
    e.last_calibrated_on = calibrated_on
    e.due_on = expires_on
    e.last_reminder_on = None
    if e.status in (EquipmentStatus.OUT_OF_SERVICE, EquipmentStatus.SENT_FOR_CALIBRATION) and expires_on >= date.today():
        await record_transition(
            db, ENTITY, e.id, e.status, EquipmentStatus.IN_SERVICE, user_id, f"Calibrated ({cert.certificate_number})"
        )
        e.status = EquipmentStatus.IN_SERVICE
    await db.flush()
    return cert


# --- reminders ---------------------------------------------------------------------------------------


async def due_reminders(db: AsyncSession, today: date | None = None) -> int:
    """Notify custodians of in-service equipment due within its reminder window or overdue.

    One reminder per piece per week; a new certificate resets it. Returns how many were sent.
    """
    today = today or date.today()
    rows = (
        await db.execute(
            select(Equipment).where(
                Equipment.status == EquipmentStatus.IN_SERVICE,
                Equipment.requires_calibration.is_(True),
                Equipment.custodian_id.is_not(None),
                Equipment.due_on.is_not(None),
            )
        )
    ).scalars()
    sent = 0
    for e in rows:
        assert e.due_on is not None and e.custodian_id is not None
        if e.due_on > today + timedelta(days=e.reminder_days):
            continue
        if e.last_reminder_on and e.last_reminder_on > today - timedelta(days=7):
            continue
        days = (e.due_on - today).days
        when = (
            f"calibration overdue since {e.due_on.isoformat()}"
            if days < 0
            else ("calibration due today" if days == 0 else f"calibration due in {days} days ({e.due_on.isoformat()})")
        )
        await notify(
            db,
            [e.custodian_id],
            Category.DUE,
            f"{e.code} {e.name}: {when}",
            body="Readings taken with it are refused once the calibration lapses.",
            link=link_of(e),
            entity=(ENTITY, e.id),
        )
        e.last_reminder_on = today
        sent += 1
    await db.commit()
    return sent


async def uncalibrated_equipment(db: AsyncSession, project_id: int, node_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """The MDR gate: the project's equipment that is overdue, uncertified, quarantined or away for calibration
    today. Equipment taken out of service is history and doesn't count. Equipment isn't anchored to asset
    nodes, so the whole project is checked whatever ``node_ids`` the dossier has."""
    rows = (
        await db.execute(
            select(Equipment)
            .where(Equipment.project_id == project_id, Equipment.status != EquipmentStatus.OUT_OF_SERVICE.value)
            .order_by(Equipment.code)
        )
    ).scalars()
    today = date.today()
    return [
        {"reference": e.code, "message": problem, "link": link_of(e)}
        for e in rows
        if (problem := problem_on(e, today)) is not None
    ]
