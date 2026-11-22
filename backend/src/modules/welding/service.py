"""Welding and NDE rules: qualification blocking, NDE sampling, progressive examination, repairs, rates."""

import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import assert_transition, next_reference, record_transition
from ..asset_tree import service as tree
from ..asset_tree.models import AssetItem, AssetNode, ItemType
from ..calibration.service import assert_calibrated
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..materials.service import unverified_heats_for_items
from .constants import (
    DEFAULT_NDE_RATES,
    JOINT_ENTITY,
    NDE_REQUEST_ENTITY,
    NDE_REQUEST_FLOW,
    SAMPLING_REASONS,
    WELD_ENTITY,
    WELD_ITEM_TYPE,
    WPS_ENTITY,
    WPS_FLOW,
    BoltedJointStatus,
    JointEventKind,
    NdeReason,
    NdeRequestStatus,
    NdeResultValue,
    QualificationState,
    QualificationStatus,
    VisualResult,
    WelderStatus,
    WeldStatus,
    WpsStatus,
)
from .models import (
    BoltedJoint,
    ContinuityEntry,
    JointEvent,
    NdeRequest,
    NdeResult,
    Qualification,
    Weld,
    Welder,
    WeldingSettings,
    WeldPass,
    WeldRepair,
    Wps,
)
from .schemas import BoltedJointRead, NdeRequestRead, NdeResultRead, QualificationRead, WelderRead, WeldRead


class NotFound(ResourceNotFoundError):
    public_detail = "Not found."


class Duplicate(ResourceExistsError):
    public_detail = "That number is already used on this project."


class WeldingRuleError(ValidationError):
    public_detail = "That breaks a welding rule."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


async def get(db: AsyncSession, model: Any, row_id: int) -> Any:
    row = await db.get(model, row_id)
    if row is None:
        raise NotFound(f"{model.__tablename__} {row_id}")
    return row


async def check_file(db: AsyncSession, file_id: int | None, project_id: int) -> None:
    if file_id is None:
        return
    f = await db.get(StoredFile, file_id)
    if f is None or (f.project_id is not None and f.project_id != project_id):
        raise WeldingRuleError("That file isn't in this project's files.")


# --- settings ----------------------------------------------------------------------------------------


async def settings_for(db: AsyncSession, project_id: int) -> WeldingSettings:
    s = await db.get(WeldingSettings, project_id)
    if s is None:
        s = WeldingSettings(project_id=project_id, nde_rates={k: dict(v) for k, v in DEFAULT_NDE_RATES.items()})
        db.add(s)
        await db.flush()
    return s


def rates_for(s: WeldingSettings, category: str) -> dict[str, float]:
    return {k: float(v) for k, v in (s.nde_rates.get(category) or {}).items() if float(v) > 0}


# --- WPS ---------------------------------------------------------------------------------------------


async def change_wps_status(db: AsyncSession, wps: Wps, target: str, note: str | None, user_id: int) -> None:
    if target == wps.status:
        return
    assert_transition(WPS_FLOW, wps.status, target)
    if target == WpsStatus.APPROVED:
        wps.approved_by_id = user_id
        wps.approved_at = datetime.now(UTC)
    await record_transition(db, WPS_ENTITY, wps.id, wps.status, target, user_id, note)
    wps.status = target
    await db.flush()


def _within(value: Decimal | None, low: Decimal | None, high: Decimal | None) -> bool:
    if value is None:
        return True
    return (low is None or value >= low) and (high is None or value <= high)


def wps_problems(wps: Wps | None, weld: Weld) -> list[str]:
    if wps is None:
        return [f"Weld {weld.weld_number} has no WPS"]
    problems = []
    if wps.status != WpsStatus.APPROVED:
        problems.append(f"WPS {wps.code} rev {wps.revision} is {wps.status}, not approved")
    if not _within(weld.thickness, wps.thickness_min, wps.thickness_max):
        problems.append(f"thickness {weld.thickness} mm is outside WPS {wps.code}'s range")
    if not _within(weld.diameter, wps.diameter_min, wps.diameter_max):
        problems.append(f"diameter {weld.diameter}in is outside WPS {wps.code}'s range")
    if wps.joint_types and weld.joint_type not in wps.joint_types:
        problems.append(f"WPS {wps.code} does not cover {weld.joint_type} joints")
    return problems


# --- qualifications ----------------------------------------------------------------------------------


def continuity_until(q: Qualification, continuity_days: int) -> date:
    return (q.continuity_last_on or q.qualified_on) + timedelta(days=continuity_days)


def qualification_state(q: Qualification, continuity_days: int, today: date | None = None) -> str:
    today = today or date.today()
    if q.status == QualificationStatus.SUSPENDED:
        return QualificationState.SUSPENDED
    if q.status == QualificationStatus.REVOKED:
        return QualificationState.REVOKED
    if q.expires_on and q.expires_on < today:
        return QualificationState.EXPIRED
    until = continuity_until(q, continuity_days)
    if until < today:
        return QualificationState.LAPSED
    soon = today + timedelta(days=30)
    if (q.expires_on and q.expires_on <= soon) or until <= soon:
        return QualificationState.EXPIRING
    return QualificationState.VALID


def _qualification_problem(q: Qualification, wps: Wps, weld: Weld, on: date, continuity_days: int) -> str | None:
    if q.status != QualificationStatus.VALID:
        return f"qualification is {q.status}"
    if q.qualified_on > on:
        return f"qualified only from {q.qualified_on.isoformat()}"
    if q.expires_on and q.expires_on < on:
        return f"qualification expired {q.expires_on.isoformat()}"
    if continuity_until(q, continuity_days) < on:
        last = (q.continuity_last_on or q.qualified_on).isoformat()
        return f"continuity lapsed (last welded with {q.process} on {last})"
    if q.positions and weld.position and weld.position not in q.positions:
        return f"not qualified for position {weld.position}"
    if not _within(weld.thickness, q.thickness_min, q.thickness_max):
        return f"not qualified for {weld.thickness} mm"
    if q.diameter_min is not None and weld.diameter is not None and weld.diameter < q.diameter_min:
        return f"not qualified below {q.diameter_min}in"
    if q.material_groups and wps.base_material_group and wps.base_material_group not in q.material_groups:
        return f"not qualified for material group {wps.base_material_group}"
    return None


async def qualification_for(
    db: AsyncSession, welder: Welder, wps: Wps, weld: Weld, on: date, continuity_days: int
) -> tuple[Qualification | None, str | None]:
    """The welder's qualification that covers this weld on the day, or why there is none."""
    if welder.status != WelderStatus.ACTIVE:
        return None, f"welder {welder.stamp} is {welder.status}"
    quals = list(
        (
            await db.execute(
                select(Qualification)
                .where(Qualification.welder_id == welder.id)
                .order_by(Qualification.expires_on.desc().nulls_first(), Qualification.id.desc())
            )
        ).scalars()
    )
    candidates = [
        q
        for q in quals
        if q.wps_id == wps.id or (q.wps_id is None and q.process.strip().upper() == wps.process.strip().upper())
    ]
    if not candidates:
        return None, f"welder {welder.stamp} has no qualification for WPS {wps.code} ({wps.process})"
    reasons = []
    for q in candidates:
        problem = _qualification_problem(q, wps, weld, on, continuity_days)
        if problem is None:
            return q, None
        reasons.append(problem)
    return None, f"welder {welder.stamp}: {reasons[0]}"


async def _qualified_welders(
    db: AsyncSession, weld: Weld, welder_ids: Iterable[int], on: date
) -> tuple[Wps, dict[int, tuple[Welder, Qualification]]]:
    """Check the WPS and every welder for the weld on the day; raise 422 listing every problem."""
    wps = await db.get(Wps, weld.wps_id) if weld.wps_id else None
    problems = wps_problems(wps, weld)
    s = await settings_for(db, weld.project_id)
    found: dict[int, tuple[Welder, Qualification]] = {}
    for welder_id in dict.fromkeys(welder_ids):
        welder = await db.get(Welder, welder_id)
        if welder is None or welder.project_id != weld.project_id:
            problems.append(f"welder {welder_id} is not on this project")
            continue
        if wps is None:
            continue
        q, problem = await qualification_for(db, welder, wps, weld, on, s.continuity_days)
        if problem:
            problems.append(problem)
        elif q:
            found[welder_id] = (welder, q)
    if problems:
        raise WeldingRuleError("Weld blocked: " + "; ".join(problems) + ".")
    assert wps is not None
    return wps, found


async def log_continuity(
    db: AsyncSession,
    welder: Welder,
    process: str,
    on: date,
    *,
    qualification: Qualification | None = None,
    weld_id: int | None = None,
    note: str | None = None,
    user_id: int | None = None,
) -> ContinuityEntry:
    """Record that the welder used the process; moves continuity on every matching valid qualification."""
    entry = ContinuityEntry(
        welder_id=welder.id,
        process=process,
        welded_on=on,
        qualification_id=qualification.id if qualification else None,
        weld_id=weld_id,
        note=note,
        recorded_by_id=user_id,
    )
    db.add(entry)
    quals = (
        await db.execute(
            select(Qualification).where(
                Qualification.welder_id == welder.id, Qualification.status == QualificationStatus.VALID.value
            )
        )
    ).scalars()
    for q in quals:
        if q.process.strip().upper() == process.strip().upper() and q.qualified_on <= on:
            if q.continuity_last_on is None or q.continuity_last_on < on:
                q.continuity_last_on = on
    await db.flush()
    return entry


# --- welds -------------------------------------------------------------------------------------------


async def _weld_item_type(db: AsyncSession, project_id: int) -> None:
    exists = await db.scalar(select(ItemType.id).where(ItemType.project_id == project_id, ItemType.key == WELD_ITEM_TYPE))
    if not exists:
        db.add(ItemType(project_id=project_id, key=WELD_ITEM_TYPE, name="Weld", field_schema={}))
        await db.flush()


async def create_weld(db: AsyncSession, values: dict[str, Any], user_id: int) -> Weld:
    project_id = values["project_id"]
    node_id = values.pop("node_id", None)
    item_id = values.pop("item_id", None)
    if item_id:
        item = await tree.get_item(db, item_id, project_id)
        if item.item_type_key != WELD_ITEM_TYPE:
            raise WeldingRuleError("That item is not a weld.")
        if await db.scalar(select(Weld.id).where(Weld.item_id == item.id)):
            raise Duplicate("That item already has weld data.")
    elif node_id:
        await _weld_item_type(db, project_id)
        item = await tree.create_item(
            db, project_id, {"node_id": node_id, "item_type_key": WELD_ITEM_TYPE, "tag": values["weld_number"]}
        )
    else:
        raise WeldingRuleError("Give the node the weld is on, or an existing weld item.")
    if await db.scalar(
        select(Weld.id).where(
            Weld.project_id == project_id,
            Weld.weld_number == values["weld_number"],
            Weld.drawing_ref.is_not_distinct_from(values.get("drawing_ref")),
        )
    ):
        raise Duplicate(values["weld_number"])
    wps = await db.get(Wps, values["wps_id"]) if values.get("wps_id") else None
    if values.get("wps_id") and (wps is None or wps.project_id != project_id):
        raise WeldingRuleError("That WPS is not on this project.")
    if values.get("pwht_required") is None:
        values["pwht_required"] = bool(wps and wps.pwht)
    if values.get("nde_required") is None:
        values["nde_required"] = rates_for(await settings_for(db, project_id), values.get("weld_category") or "normal")
    else:
        values["nde_required"] = {str(k): float(v) for k, v in values["nde_required"].items() if float(v) > 0}
    weld = Weld(item_id=item.id, **values)
    db.add(weld)
    await db.flush()
    await record_transition(db, WELD_ENTITY, weld.id, None, weld.status, user_id, None)
    return weld


async def update_weld(db: AsyncSession, weld: Weld, changes: dict[str, Any]) -> None:
    if weld.status in (WeldStatus.ACCEPTED, WeldStatus.CUT_OUT) and set(changes) - {"notes", "drawing_ref", "line_ref"}:
        raise WeldingRuleError(f"Weld {weld.weld_number} is {weld.status}; only notes and references can change.")
    if "wps_id" in changes and changes["wps_id"]:
        wps = await db.get(Wps, changes["wps_id"])
        if wps is None or wps.project_id != weld.project_id:
            raise WeldingRuleError("That WPS is not on this project.")
    if "nde_required" in changes and changes["nde_required"] is not None:
        changes["nde_required"] = {str(k): float(v) for k, v in changes["nde_required"].items() if float(v) > 0}
    elif "weld_category" in changes and changes["weld_category"] != weld.weld_category:
        changes["nde_required"] = rates_for(await settings_for(db, weld.project_id), changes["weld_category"])
    for k, v in changes.items():
        if k == "nde_required" and v is None:
            continue
        setattr(weld, k, v)
    await db.flush()


async def _set_status(db: AsyncSession, weld: Weld, target: str, user_id: int | None, note: str | None = None) -> None:
    if weld.status != target:
        await record_transition(db, WELD_ENTITY, weld.id, weld.status, target, user_id, note)
        weld.status = target


async def _add_result(db: AsyncSession, weld: Weld, method: str, reason: str, **kw: Any) -> NdeResult:
    r = NdeResult(project_id=weld.project_id, weld_id=weld.id, method=method, reason=reason, **kw)
    db.add(r)
    await db.flush()
    return r


async def refresh_status(db: AsyncSession, weld: Weld, user_id: int | None) -> None:
    """Welded / NDE pending / rejected from the visual and NDE results of the current repair."""
    if weld.status in (WeldStatus.FIT_UP, WeldStatus.ACCEPTED, WeldStatus.CUT_OUT):
        return
    results = list(
        (
            await db.execute(select(NdeResult).where(NdeResult.weld_id == weld.id, NdeResult.repair_seq == weld.repair_count))
        ).scalars()
    )
    if weld.visual_result == VisualResult.REJECTED or any(r.result == NdeResultValue.REJECTED for r in results):
        target = WeldStatus.REJECTED
    elif any(r.result == NdeResultValue.PENDING for r in results):
        target = WeldStatus.NDE_PENDING
    else:
        target = WeldStatus.WELDED
    await _set_status(db, weld, target, user_id)


async def record_welding(db: AsyncSession, weld: Weld, welded_on: date, passes: list[dict[str, Any]], user_id: int) -> None:
    """Who welded it, when. Blocked (422) unless the WPS is approved and every welder is qualified that day."""
    if weld.status != WeldStatus.FIT_UP:
        raise WeldingRuleError(f"Weld {weld.weld_number} is already {weld.status}.")
    if welded_on > date.today():
        raise WeldingRuleError("The weld date can't be in the future.")
    wps, found = await _qualified_welders(db, weld, [p["welder_id"] for p in passes], welded_on)
    for p in passes:
        welder, q = found[p["welder_id"]]
        db.add(WeldPass(weld_id=weld.id, welder_id=welder.id, pass_name=p.get("pass_name") or "all", qualification_id=q.id))
    for welder, q in found.values():
        await log_continuity(db, welder, q.process, welded_on, qualification=q, weld_id=weld.id, user_id=user_id)
    weld.welded_on = welded_on
    await _set_status(db, weld, WeldStatus.WELDED, user_id)
    for method, pct in (weld.nde_required or {}).items():
        if float(pct) >= 100:
            await _add_result(db, weld, method, NdeReason.FULL)
    await refresh_status(db, weld, user_id)
    await db.flush()


async def record_visual(db: AsyncSession, weld: Weld, result: str, on: date | None, note: str | None, user_id: int) -> None:
    if weld.status in (WeldStatus.FIT_UP, WeldStatus.ACCEPTED, WeldStatus.CUT_OUT):
        raise WeldingRuleError(f"Weld {weld.weld_number} is {weld.status}; visual inspection doesn't apply.")
    weld.visual_result = result
    weld.visual_on = on or date.today()
    await refresh_status(db, weld, user_id)
    await db.flush()


async def record_pwht(db: AsyncSession, weld: Weld, done_on: date) -> None:
    if weld.welded_on is None or done_on < weld.welded_on:
        raise WeldingRuleError("PWHT comes after welding.")
    weld.pwht_on = done_on
    await db.flush()


async def welders_of(db: AsyncSession, weld_ids: Iterable[int], repair_seq: int | None = 0) -> dict[int, set[int]]:
    ids = list(weld_ids)
    if not ids:
        return {}
    stmt = select(WeldPass.weld_id, WeldPass.welder_id).where(WeldPass.weld_id.in_(ids))
    if repair_seq is not None:
        stmt = stmt.where(WeldPass.repair_seq == repair_seq)
    out: dict[int, set[int]] = defaultdict(set)
    for weld_id, welder_id in (await db.execute(stmt)).tuples().all():
        out[weld_id].add(welder_id)
    return out


async def repair(db: AsyncSession, weld: Weld, values: dict[str, Any], user_id: int) -> WeldRepair:
    """R1, R2...: a rejected weld repaired by the same or new (qualified) welders; re-examined by each rejected method."""
    if weld.status != WeldStatus.REJECTED:
        raise WeldingRuleError(f"Weld {weld.weld_number} is {weld.status}; only a rejected weld is repaired.")
    s = await settings_for(db, weld.project_id)
    seq = weld.repair_count + 1
    if seq > s.max_repairs:
        raise WeldingRuleError(
            f"Weld {weld.weld_number} has had {weld.repair_count} repairs (limit {s.max_repairs}): cut it out and re-weld."
        )
    on: date = values["repaired_on"]
    _, found = await _qualified_welders(db, weld, values["welder_ids"], on)
    rejected = list(
        (
            await db.execute(
                select(NdeResult).where(
                    NdeResult.weld_id == weld.id,
                    NdeResult.repair_seq == weld.repair_count,
                    NdeResult.result == NdeResultValue.REJECTED.value,
                )
            )
        ).scalars()
    )
    rec = WeldRepair(
        weld_id=weld.id,
        seq=seq,
        repaired_on=on,
        defect=values.get("defect"),
        cause_result_id=rejected[0].id if rejected else None,
        notes=values.get("notes"),
        recorded_by_id=user_id,
    )
    db.add(rec)
    for welder, q in found.values():
        db.add(WeldPass(weld_id=weld.id, welder_id=welder.id, pass_name="repair", repair_seq=seq, qualification_id=q.id))
        await log_continuity(db, welder, q.process, on, qualification=q, weld_id=weld.id, user_id=user_id)
    weld.repair_count = seq
    if weld.visual_result == VisualResult.REJECTED:
        weld.visual_result = VisualResult.PENDING
    for method in dict.fromkeys(r.method for r in rejected):
        await _add_result(db, weld, method, NdeReason.REPAIR, repair_seq=seq)
    await _set_status(db, weld, WeldStatus.WELDED, user_id, f"R{seq}")
    await refresh_status(db, weld, user_id)
    await db.flush()
    return rec


async def _unverified_heats(db: AsyncSession, weld: Weld) -> list[str]:
    if not await is_enabled(db, "materials", weld.project_id):
        return []
    return await unverified_heats_for_items(db, [weld.item_id])


async def accept(db: AsyncSession, weld: Weld, user_id: int, note: str | None = None) -> None:
    """Final acceptance: visual accepted, PWHT done when required, every examination of the current repair accepted."""
    problems = []
    if weld.status != WeldStatus.WELDED:
        problems.append(f"weld is {weld.status.replace('_', ' ')}")
    if weld.visual_result != VisualResult.ACCEPTED:
        problems.append("visual inspection is not accepted")
    if weld.pwht_required and weld.pwht_on is None:
        problems.append("PWHT is not recorded")
    wps = await db.get(Wps, weld.wps_id) if weld.wps_id else None
    if wps is None or wps.status != WpsStatus.APPROVED:
        problems.append("the WPS is not approved")
    results = list(
        (
            await db.execute(select(NdeResult).where(NdeResult.weld_id == weld.id, NdeResult.repair_seq == weld.repair_count))
        ).scalars()
    )
    for method, pct in (weld.nde_required or {}).items():
        if float(pct) >= 100 and not any(r.method == method and r.result == NdeResultValue.ACCEPTED for r in results):
            problems.append(f"100 % {method.upper()} has no accepted result")
    heats = await _unverified_heats(db, weld)
    if heats:
        problems.append("material without a verified certificate: " + ", ".join(heats))
    if problems:
        raise WeldingRuleError(f"Weld {weld.weld_number} can't be accepted: " + "; ".join(problems) + ".")
    weld.accepted_on = date.today()
    weld.accepted_by_id = user_id
    await _set_status(db, weld, WeldStatus.ACCEPTED, user_id, note)
    await db.flush()


async def cut_out(db: AsyncSession, weld: Weld, user_id: int, note: str | None) -> None:
    if weld.status in (WeldStatus.ACCEPTED, WeldStatus.CUT_OUT, WeldStatus.FIT_UP):
        raise WeldingRuleError(f"Weld {weld.weld_number} is {weld.status}; it can't be cut out.")
    for r in (
        await db.execute(
            select(NdeResult).where(NdeResult.weld_id == weld.id, NdeResult.result == NdeResultValue.PENDING.value)
        )
    ).scalars():
        await db.delete(r)
    await _set_status(db, weld, WeldStatus.CUT_OUT, user_id, note)
    await db.flush()


# --- NDE sampling ------------------------------------------------------------------------------------


async def sampling(db: AsyncSession, project_id: int, method: str) -> dict[str, Any]:
    """Per welder lot (welds of the welder with the same percentage for the method), how many must be examined.

    A weld examined (or picked) for one of its welders counts for all of them. The proposal fills
    each lot's shortfall with the earliest welded welds not yet examined by the method.
    """
    welds = [
        w
        for w in (
            await db.execute(
                select(Weld)
                .where(
                    Weld.project_id == project_id,
                    Weld.status.in_([WeldStatus.WELDED, WeldStatus.NDE_PENDING, WeldStatus.ACCEPTED, WeldStatus.REJECTED]),
                )
                .order_by(Weld.welded_on, Weld.id)
            )
        ).scalars()
        if float((w.nde_required or {}).get(method, 0)) > 0
    ]
    by_id = {w.id: w for w in welds}
    welders = await welders_of(db, by_id)
    sampled: set[int] = set()
    any_exam: set[int] = set()
    pending_free: list[int] = []
    for r in (
        await db.execute(select(NdeResult).where(NdeResult.project_id == project_id, NdeResult.method == method))
    ).scalars():
        any_exam.add(r.weld_id)
        if r.reason in SAMPLING_REASONS:
            sampled.add(r.weld_id)
        if r.result == NdeResultValue.PENDING and r.request_id is None:
            pending_free.append(r.weld_id)
    lots: dict[tuple[int, float], list[Weld]] = defaultdict(list)
    for w in welds:
        for welder_id in welders.get(w.id, ()):
            lots[(welder_id, float(w.nde_required[method]))].append(w)
    stamps = dict(
        (await db.execute(select(Welder.id, Welder.stamp).where(Welder.id.in_({k[0] for k in lots} or {0})))).tuples().all()
    )
    picked: list[int] = []
    out = []
    for (welder_id, pct), lot in sorted(lots.items(), key=lambda kv: (stamps.get(kv[0][0], ""), kv[0][1])):
        required = math.ceil(len(lot) * pct / 100 - 1e-9)
        selected = sum(1 for w in lot if w.id in sampled or w.id in picked)
        shortfall = max(0, required - selected)
        for w in lot:
            if shortfall <= 0:
                break
            if w.id in any_exam or w.id in picked or w.status not in (WeldStatus.WELDED, WeldStatus.NDE_PENDING):
                continue
            picked.append(w.id)
            shortfall -= 1
        out.append(
            {
                "welder_id": welder_id,
                "stamp": stamps.get(welder_id, "?"),
                "percent": pct,
                "welds": len(lot),
                "required": required,
                "selected": selected,
                "shortfall": max(0, required - selected),
            }
        )
    return {"method": method, "lots": out, "proposed_weld_ids": picked, "pending_weld_ids": sorted(set(pending_free))}


async def create_request(db: AsyncSession, values: dict[str, Any], user_id: int) -> NdeRequest:
    project_id, method = values["project_id"], str(values["method"])
    req = NdeRequest(
        project_id=project_id,
        code=await next_reference(db, "NDE", project_id),
        method=method,
        requested_on=values.get("requested_on") or date.today(),
        required_by=values.get("required_by"),
        contractor=values.get("contractor"),
        notes=values.get("notes"),
        created_by_id=user_id,
    )
    db.add(req)
    await db.flush()
    count = 0
    for weld_id in dict.fromkeys(values.get("weld_ids") or []):
        weld = await db.get(Weld, weld_id)
        if weld is None or weld.project_id != project_id:
            raise WeldingRuleError(f"Weld {weld_id} is not on this project.")
        if weld.status not in (WeldStatus.WELDED, WeldStatus.NDE_PENDING):
            raise WeldingRuleError(f"Weld {weld.weld_number} is {weld.status}; it can't be sent for NDE.")
        pending = await db.scalar(
            select(NdeResult).where(
                NdeResult.weld_id == weld.id, NdeResult.method == method, NdeResult.result == NdeResultValue.PENDING.value
            )
        )
        if pending is not None:
            if pending.request_id is None:
                pending.request_id = req.id
                count += 1
            continue
        await _add_result(
            db, weld, method, str(values.get("reason") or NdeReason.RANDOM), repair_seq=weld.repair_count, request_id=req.id
        )
        await refresh_status(db, weld, user_id)
        count += 1
    if values.get("include_pending", True):
        for r in (
            await db.execute(
                select(NdeResult).where(
                    NdeResult.project_id == project_id,
                    NdeResult.method == method,
                    NdeResult.result == NdeResultValue.PENDING.value,
                    NdeResult.request_id.is_(None),
                )
            )
        ).scalars():
            r.request_id = req.id
            count += 1
    if not count:
        raise WeldingRuleError("Nothing to examine: pick welds or include pending examinations.")
    await record_transition(db, NDE_REQUEST_ENTITY, req.id, None, req.status, user_id, None)
    await db.flush()
    return req


async def change_request_status(db: AsyncSession, req: NdeRequest, target: str, note: str | None, user_id: int) -> None:
    if target == req.status:
        return
    assert_transition(NDE_REQUEST_FLOW, req.status, target)
    pending = await db.scalar(
        select(func.count()).where(NdeResult.request_id == req.id, NdeResult.result == NdeResultValue.PENDING.value)
    )
    if target == NdeRequestStatus.COMPLETED and pending:
        raise WeldingRuleError(f"{req.code} still has {pending} examinations without a result.")
    if target == NdeRequestStatus.CANCELLED:
        for r in (
            await db.execute(
                select(NdeResult).where(NdeResult.request_id == req.id, NdeResult.result == NdeResultValue.PENDING.value)
            )
        ).scalars():
            r.request_id = None
    await record_transition(db, NDE_REQUEST_ENTITY, req.id, req.status, target, user_id, note)
    req.status = target
    await db.flush()


async def _progressive(db: AsyncSession, rejected: NdeResult, weld: Weld, s: WeldingSettings) -> list[NdeResult]:
    """After a rejected sample: two more welds of the same welder(s) (tier 1, then tier 2), then all of them."""
    if rejected.repair_seq != 0 or rejected.reason not in (NdeReason.RANDOM, NdeReason.PROGRESSIVE, NdeReason.CLIENT):
        return []
    tier = rejected.tier + 1
    if tier > 3:
        return []
    welder_ids = (await welders_of(db, [weld.id])).get(weld.id, set())
    if not welder_ids:
        return []
    same_welder = set(
        (
            await db.execute(select(WeldPass.weld_id).where(WeldPass.welder_id.in_(welder_ids), WeldPass.repair_seq == 0))
        ).scalars()
    )
    examined = set(
        (
            await db.execute(
                select(NdeResult.weld_id).where(NdeResult.project_id == weld.project_id, NdeResult.method == rejected.method)
            )
        ).scalars()
    )
    candidates = [
        w
        for w in (
            await db.execute(
                select(Weld)
                .where(
                    Weld.id.in_(same_welder - examined - {weld.id}),
                    Weld.status.in_([WeldStatus.WELDED, WeldStatus.NDE_PENDING, WeldStatus.ACCEPTED]),
                )
                .order_by(Weld.welded_on, Weld.id)
            )
        ).scalars()
    ]
    chosen = candidates if tier == 3 else candidates[: s.progressive_count]
    added = []
    for w in chosen:
        added.append(await _add_result(db, w, rejected.method, NdeReason.PROGRESSIVE, tier=tier, triggered_by_id=rejected.id))
        if w.status == WeldStatus.ACCEPTED:
            # An accepted weld drawn into progressive examination is open again until it passes.
            await _set_status(db, w, WeldStatus.NDE_PENDING, None, f"Progressive examination after {weld.weld_number}")
            w.accepted_on = None
        else:
            await refresh_status(db, w, None)
    return added


async def record_result(
    db: AsyncSession, r: NdeResult, values: dict[str, Any], user_id: int
) -> tuple[Weld, list[NdeResult], str | None]:
    if r.result != NdeResultValue.PENDING:
        raise WeldingRuleError("That examination already has a result.")
    if values["result"] == NdeResultValue.PENDING:
        raise WeldingRuleError("Record accepted or rejected.")
    await check_file(db, values.get("file_id"), r.project_id)
    weld = await get(db, Weld, r.weld_id)
    for key in ("result", "examined_on", "report_ref", "file_id", "technician", "defect"):
        if key in values:
            setattr(r, key, str(values[key]) if key == "result" else values[key])
    added: list[NdeResult] = []
    message = None
    s = await settings_for(db, weld.project_id)
    if r.result == NdeResultValue.REJECTED:
        added = await _progressive(db, r, weld, s)
        if added:
            message = f"Rejected: {len(added)} more weld(s) of the same welder added for {r.method.upper()}" + (
                " (100 % of the welder's welds)." if r.tier + 1 == 3 else "."
            )
        if weld.repair_count >= s.max_repairs:
            message = (message + " " if message else "") + f"{weld.weld_number} has reached the repair limit: cut it out."
    await refresh_status(db, weld, user_id)
    await db.flush()
    return weld, added, message


# --- repair rates ------------------------------------------------------------------------------------


def _rate(examined: int, rejected: int) -> float | None:
    return round(rejected / examined * 100, 2) if examined else None


async def repair_rates(db: AsyncSession, project_id: int, method: str | None = None) -> dict[str, Any]:
    """Rejected examinations / examinations with a result, per welder (of the pass examined) and per method."""
    stmt = select(NdeResult).where(NdeResult.project_id == project_id, NdeResult.result != NdeResultValue.PENDING.value)
    if method:
        stmt = stmt.where(NdeResult.method == method)
    results = list((await db.execute(stmt)).scalars())
    passes = defaultdict(set)
    if results:
        for weld_id, seq, welder_id in (
            (
                await db.execute(
                    select(WeldPass.weld_id, WeldPass.repair_seq, WeldPass.welder_id).where(
                        WeldPass.weld_id.in_({r.weld_id for r in results})
                    )
                )
            )
            .tuples()
            .all()
        ):
            passes[(weld_id, seq)].add(welder_id)
    by_welder: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    by_method: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in results:
        bad = int(r.result == NdeResultValue.REJECTED)
        by_method[r.method][0] += 1
        by_method[r.method][1] += bad
        for welder_id in passes.get((r.weld_id, r.repair_seq), ()):
            by_welder[welder_id][0] += 1
            by_welder[welder_id][1] += bad
    welders = {w.id: w for w in (await db.execute(select(Welder).where(Welder.id.in_(set(by_welder) or {0})))).scalars()}
    total = [sum(v[0] for v in by_method.values()), sum(v[1] for v in by_method.values())]
    return {
        "by_welder": sorted(
            (
                {
                    "key": str(wid),
                    "label": f"{welders[wid].stamp} {welders[wid].name}" if wid in welders else str(wid),
                    "examined": n,
                    "rejected": bad,
                    "rate": _rate(n, bad),
                }
                for wid, (n, bad) in by_welder.items()
            ),
            key=lambda row: (-(row["rate"] or 0), row["label"]),
        ),
        "by_method": [
            {"key": m, "label": m.upper(), "examined": n, "rejected": bad, "rate": _rate(n, bad)}
            for m, (n, bad) in sorted(by_method.items())
        ],
        "overall": {"key": "all", "label": "All", "examined": total[0], "rejected": total[1], "rate": _rate(*total)},
    }


# --- reads -------------------------------------------------------------------------------------------


def repair_label(n: int) -> str:
    return f"R{n}" if n else ""


async def read_welds(db: AsyncSession, welds: list[Weld]) -> list[dict[str, Any]]:
    ids = [w.id for w in welds]
    items = {
        i.id: i
        for i in (await db.execute(select(AssetItem).where(AssetItem.id.in_({w.item_id for w in welds} or {0})))).scalars()
    }
    nodes = {
        n.id: n
        for n in (
            await db.execute(select(AssetNode).where(AssetNode.id.in_({i.node_id for i in items.values()} or {0})))
        ).scalars()
    }
    wps = {
        w.id: w
        for w in (await db.execute(select(Wps).where(Wps.id.in_({w.wps_id for w in welds if w.wps_id} or {0})))).scalars()
    }
    welder_map = await welders_of(db, ids)
    stamps = dict(
        (
            await db.execute(
                select(Welder.id, Welder.stamp).where(Welder.id.in_({x for s in welder_map.values() for x in s} or {0}))
            )
        )
        .tuples()
        .all()
    )
    latest: dict[int, dict[str, str]] = defaultdict(dict)
    if ids:
        for r in (await db.execute(select(NdeResult).where(NdeResult.weld_id.in_(ids)).order_by(NdeResult.id))).scalars():
            latest[r.weld_id][r.method] = r.result
    out = []
    for w in welds:
        item = items.get(w.item_id)
        node = nodes.get(item.node_id) if item else None
        out.append(
            WeldRead.model_validate(w)
            .model_copy(
                update={
                    "node_id": node.id if node else None,
                    "node_path": node.display_path if node else None,
                    "wps_code": f"{wps[w.wps_id].code} rev {wps[w.wps_id].revision}" if w.wps_id in wps else None,
                    "repair_label": repair_label(w.repair_count),
                    "welders": sorted(stamps.get(i, "?") for i in welder_map.get(w.id, ())),
                    "nde_summary": latest.get(w.id, {}),
                }
            )
            .model_dump(mode="json")
        )
    return out


async def read_results(db: AsyncSession, results: list[NdeResult]) -> list[dict[str, Any]]:
    numbers = dict(
        (await db.execute(select(Weld.id, Weld.weld_number).where(Weld.id.in_({r.weld_id for r in results} or {0}))))
        .tuples()
        .all()
    )
    codes = dict(
        (
            await db.execute(
                select(NdeRequest.id, NdeRequest.code).where(
                    NdeRequest.id.in_({r.request_id for r in results if r.request_id} or {0})
                )
            )
        )
        .tuples()
        .all()
    )
    return [
        NdeResultRead.model_validate(r)
        .model_copy(
            update={"weld_number": numbers.get(r.weld_id), "request_code": codes.get(r.request_id) if r.request_id else None}
        )
        .model_dump(mode="json")
        for r in results
    ]


async def weld_detail(db: AsyncSession, weld: Weld) -> dict[str, Any]:
    base = (await read_welds(db, [weld]))[0]
    passes = list(
        (
            await db.execute(select(WeldPass).where(WeldPass.weld_id == weld.id).order_by(WeldPass.repair_seq, WeldPass.id))
        ).scalars()
    )
    stamps = dict(
        (await db.execute(select(Welder.id, Welder.stamp).where(Welder.id.in_({p.welder_id for p in passes} or {0}))))
        .tuples()
        .all()
    )
    repairs = list(
        (await db.execute(select(WeldRepair).where(WeldRepair.weld_id == weld.id).order_by(WeldRepair.seq))).scalars()
    )
    results = list((await db.execute(select(NdeResult).where(NdeResult.weld_id == weld.id).order_by(NdeResult.id))).scalars())
    return {
        **base,
        "passes": [
            {
                "id": p.id,
                "welder_id": p.welder_id,
                "welder_stamp": stamps.get(p.welder_id),
                "pass_name": p.pass_name,
                "repair_seq": p.repair_seq,
                "qualification_id": p.qualification_id,
            }
            for p in passes
        ],
        "repairs": [
            {
                "id": r.id,
                "seq": r.seq,
                "repaired_on": r.repaired_on,
                "defect": r.defect,
                "cause_result_id": r.cause_result_id,
                "notes": r.notes,
            }
            for r in repairs
        ],
        "nde": await read_results(db, results),
    }


async def read_requests(db: AsyncSession, reqs: list[NdeRequest]) -> list[dict[str, Any]]:
    counts: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    if reqs:
        for req_id, result, n in (
            (
                await db.execute(
                    select(NdeResult.request_id, NdeResult.result, func.count())
                    .where(NdeResult.request_id.in_([r.id for r in reqs]))
                    .group_by(NdeResult.request_id, NdeResult.result)
                )
            )
            .tuples()
            .all()
        ):
            c = counts[req_id or 0]
            c[0] += n
            if result == NdeResultValue.PENDING:
                c[1] += n
            if result == NdeResultValue.REJECTED:
                c[2] += n
    return [
        NdeRequestRead.model_validate(r)
        .model_copy(update={"total": counts[r.id][0], "pending": counts[r.id][1], "rejected": counts[r.id][2]})
        .model_dump(mode="json")
        for r in reqs
    ]


async def read_qualifications(db: AsyncSession, quals: list[Qualification], project_id: int) -> list[dict[str, Any]]:
    s = await settings_for(db, project_id)
    today = date.today()
    return [
        QualificationRead.model_validate(q)
        .model_copy(
            update={
                "continuity_until": continuity_until(q, s.continuity_days),
                "state": qualification_state(q, s.continuity_days, today),
            }
        )
        .model_dump(mode="json")
        for q in quals
    ]


async def read_welders(db: AsyncSession, welders: list[Welder], project_id: int) -> list[dict[str, Any]]:
    s = await settings_for(db, project_id)
    usable: dict[int, set[str]] = defaultdict(set)
    if welders:
        for q in (
            await db.execute(select(Qualification).where(Qualification.welder_id.in_([w.id for w in welders])))
        ).scalars():
            if qualification_state(q, s.continuity_days) in (QualificationState.VALID, QualificationState.EXPIRING):
                usable[q.welder_id].add(q.process)
    return [
        WelderRead.model_validate(w).model_copy(update={"processes": sorted(usable[w.id])}).model_dump(mode="json")
        for w in welders
    ]


_RANK = {
    QualificationState.VALID: 0,
    QualificationState.EXPIRING: 1,
    QualificationState.LAPSED: 2,
    QualificationState.EXPIRED: 3,
    QualificationState.SUSPENDED: 4,
    QualificationState.REVOKED: 5,
}


async def matrix(db: AsyncSession, project_id: int) -> dict[str, Any]:
    """Welders by process: the best qualification state on the day."""
    s = await settings_for(db, project_id)
    welders = list((await db.execute(select(Welder).where(Welder.project_id == project_id).order_by(Welder.stamp))).scalars())
    quals = list(
        (await db.execute(select(Qualification).where(Qualification.welder_id.in_([w.id for w in welders] or [0])))).scalars()
    )
    processes = sorted({q.process for q in quals})
    best: dict[tuple[int, str], tuple[str, Qualification]] = {}
    for q in quals:
        state = qualification_state(q, s.continuity_days)
        key = (q.welder_id, q.process)
        if key not in best or _RANK[QualificationState(state)] < _RANK[QualificationState(best[key][0])]:
            best[key] = (state, q)
    rows = []
    for w in welders:
        cells = {}
        for p in processes:
            if (w.id, p) in best:
                state, q = best[(w.id, p)]
                cells[p] = {
                    "state": state,
                    "qualification_id": q.id,
                    "expires_on": q.expires_on,
                    "continuity_until": continuity_until(q, s.continuity_days),
                }
        rows.append({"welder_id": w.id, "stamp": w.stamp, "name": w.name, "status": w.status, "cells": cells})
    return {"processes": processes, "rows": rows}


# --- bolted joints -----------------------------------------------------------------------------------


async def create_joint(db: AsyncSession, values: dict[str, Any], user_id: int) -> BoltedJoint:
    project_id = values["project_id"]
    await tree.get_node(db, values["node_id"], project_id)
    if values.get("item_id"):
        await tree.get_item(db, values["item_id"], project_id)
    if await db.scalar(
        select(BoltedJoint.id).where(BoltedJoint.project_id == project_id, BoltedJoint.joint_ref == values["joint_ref"])
    ):
        raise Duplicate(values["joint_ref"])
    joint = BoltedJoint(**{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()})
    db.add(joint)
    await db.flush()
    await record_transition(db, JOINT_ENTITY, joint.id, None, joint.status, user_id, None)
    return joint


async def record_joint_event(db: AsyncSession, joint: BoltedJoint, values: dict[str, Any], user_id: int) -> JointEvent:
    """A breakout or make-up of this joint (TD-590: recorded per joint).

    A make-up needs the tools used, which must pass the calibration gate on the day, and an applied
    value within the joint's tolerance of its target.
    """
    kind = str(values["kind"])
    on: date = values["performed_on"]
    if on > date.today():
        raise WeldingRuleError("The date can't be in the future.")
    if kind == JointEventKind.BREAKOUT:
        if joint.status != BoltedJointStatus.MADE_UP:
            raise WeldingRuleError(
                f"Joint {joint.joint_ref} is {joint.status.replace('_', ' ')}; only a made-up joint is broken out."
            )
        target = BoltedJointStatus.BROKEN_OUT
    else:
        if joint.status == BoltedJointStatus.MADE_UP:
            raise WeldingRuleError(f"Joint {joint.joint_ref} is already made up: record its breakout first.")
        if not values.get("equipment_ids"):
            raise WeldingRuleError("Record the torque wrench or tensioning tool used.")
        if values.get("applied_value") is None:
            raise WeldingRuleError("Record the applied torque or tension.")
        if await is_enabled(db, "calibration", joint.project_id):
            await assert_calibrated(db, values["equipment_ids"], on, project_id=joint.project_id)
        if joint.target_value is not None:
            applied, goal = Decimal(values["applied_value"]), joint.target_value
            band = goal * joint.tolerance_pct / 100
            if abs(applied - goal) > band:
                raise WeldingRuleError(
                    f"Applied {applied} {joint.unit} is outside {goal} ± {joint.tolerance_pct} %: re-tighten first."
                )
        target = BoltedJointStatus.MADE_UP
    event = JointEvent(
        joint_id=joint.id,
        kind=kind,
        performed_on=on,
        performed_by=values.get("performed_by"),
        equipment_ids=list(values.get("equipment_ids") or []),
        applied_value=values.get("applied_value"),
        pass_values=[str(v) for v in values.get("pass_values") or []],
        gasket_replaced=bool(values.get("gasket_replaced")),
        reason=values.get("reason"),
        notes=values.get("notes"),
        recorded_by_id=user_id,
    )
    db.add(event)
    await record_transition(db, JOINT_ENTITY, joint.id, joint.status, target, user_id, values.get("reason"))
    joint.status = target
    await db.flush()
    return event


async def read_joints(db: AsyncSession, joints: list[BoltedJoint]) -> list[dict[str, Any]]:
    nodes = dict(
        (
            await db.execute(
                select(AssetNode.id, AssetNode.display_path).where(AssetNode.id.in_({j.node_id for j in joints} or {0}))
            )
        )
        .tuples()
        .all()
    )
    stats: dict[int, tuple[int, date | None]] = {}
    if joints:
        for joint_id, breakouts, last in (
            (
                await db.execute(
                    select(
                        JointEvent.joint_id,
                        func.count().filter(JointEvent.kind == JointEventKind.BREAKOUT.value),
                        func.max(JointEvent.performed_on),
                    )
                    .where(JointEvent.joint_id.in_([j.id for j in joints]))
                    .group_by(JointEvent.joint_id)
                )
            )
            .tuples()
            .all()
        ):
            stats[joint_id] = (breakouts, last)
    return [
        BoltedJointRead.model_validate(j)
        .model_copy(
            update={
                "node_path": nodes.get(j.node_id),
                "breakouts": stats.get(j.id, (0, None))[0],
                "last_event_on": stats.get(j.id, (0, None))[1],
            }
        )
        .model_dump(mode="json")
        for j in joints
    ]
