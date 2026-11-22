"""Coating jobs: hold points in order, environmental readings with the dew-point rule, DFT sets, release.

A hold point (surface preparation, then each coat) is released as passed only when every rule holds:
the previous hold point passed; every environmental reading recorded against it passed (surface at
least the system's margin, 3 °C by default, above the dew point); and for a coat, its latest DFT set
passes the selected rule (80/20, 90/10 or min/max). Failing a hold point fails the job.

Every reading names the instruments used (``equipment_ids``). When a ``calibration`` module is
installed and switched on, ``calibration.service.assert_calibrated(db, equipment_id, on_date)`` is
called for each before anything is stored; it should raise to refuse an out-of-calibration instrument.
"""

import importlib
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.state import is_enabled
from ...infrastructure.records import record_transition
from ...infrastructure.records.numbering import next_reference
from ..asset_tree import service as tree
from ..asset_tree.models import AssetNode
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from ..notifications.constants import Category
from ..notifications.service import notify
from .calc import dft_stats, environment_check
from .models import CoatingJob, CoatingStage, CoatingSystem, DftSet, EnvironmentalReading
from .schemas import DftRead, EnvironmentRead, JobRead, StageRead, SystemRead

ENTITY = "coating_job"


class CoatingNotFound(ResourceNotFoundError):
    public_detail = "Coating record not found."


class SystemCodeTaken(ResourceExistsError):
    public_detail = "Another coating system on this project uses that code."


class HoldPointBlocked(ValidationError):
    public_detail = "The hold point can't be released yet."


class NotACoat(ValidationError):
    public_detail = "DFT readings belong to a coat, and the coat needs a minimum DFT."


def utcnow() -> datetime:
    return datetime.now(UTC)


async def assert_calibrated(db: AsyncSession, project_id: int, equipment_ids: list[int], on: date) -> None:
    """Ask the ``calibration`` module, when installed and on, that every instrument is in calibration."""
    if not equipment_ids:
        return
    try:
        calibration = importlib.import_module("..calibration.service", __package__)
    except ModuleNotFoundError:
        return
    check = getattr(calibration, "assert_calibrated", None)
    if check is None or not await is_enabled(db, "calibration", project_id):
        return
    for equipment_id in equipment_ids:
        await check(db, equipment_id, on)


# --- systems ------------------------------------------------------------------------------------


async def get_system(db: AsyncSession, system_id: int, project_id: int | None = None) -> CoatingSystem:
    system = await db.get(CoatingSystem, system_id)
    if system is None or (project_id is not None and system.project_id != project_id):
        raise CoatingNotFound(f"system {system_id}")
    return system


async def code_free(db: AsyncSession, project_id: int, code: str, other: int | None = None) -> None:
    taken = await db.scalar(select(CoatingSystem.id).where(CoatingSystem.project_id == project_id, CoatingSystem.code == code))
    if taken is not None and taken != other:
        raise SystemCodeTaken(code)


def read_system(s: CoatingSystem) -> dict[str, Any]:
    return SystemRead.model_validate(s).model_dump(mode="json")


# --- jobs ---------------------------------------------------------------------------------------


async def get_job(db: AsyncSession, job_id: int) -> CoatingJob:
    job = await db.get(CoatingJob, job_id)
    if job is None:
        raise CoatingNotFound(f"job {job_id}")
    return job


async def stages_of(db: AsyncSession, job_id: int) -> list[CoatingStage]:
    rows = await db.execute(select(CoatingStage).where(CoatingStage.job_id == job_id).order_by(CoatingStage.seq))
    return list(rows.scalars())


async def get_stage(db: AsyncSession, job: CoatingJob, stage_id: int) -> CoatingStage:
    stage = await db.get(CoatingStage, stage_id)
    if stage is None or stage.job_id != job.id:
        raise CoatingNotFound(f"stage {stage_id}")
    return stage


async def create_job(db: AsyncSession, values: dict[str, Any], user_id: int) -> CoatingJob:
    project_id = values["project_id"]
    system = await get_system(db, values["system_id"], project_id)
    await tree.get_node(db, values["node_id"], project_id)
    if values.get("item_id"):
        await tree.get_item(db, values["item_id"], project_id)
    rule = values.get("dft_rule")
    job = CoatingJob(
        project_id=project_id,
        code=await next_reference(db, "CJ", project_id),
        title=values["title"],
        system_id=system.id,
        node_id=values["node_id"],
        item_id=values.get("item_id"),
        area_m2=values.get("area_m2"),
        dft_rule=str(rule.value if hasattr(rule, "value") else rule) if rule else system.dft_rule,
        created_by_id=user_id,
        notes=values.get("notes"),
    )
    db.add(job)
    await db.flush()
    prep = system.surface_prep_standard or "Surface preparation"
    db.add(CoatingStage(job_id=job.id, seq=0, kind="surface_prep", name=prep))
    for i, coat in enumerate(system.coats, start=1):
        db.add(
            CoatingStage(
                job_id=job.id,
                seq=i,
                kind="coat",
                name=coat.get("name") or f"Coat {i}",
                product=coat.get("product"),
                dft_min_um=coat.get("dft_min_um"),
                dft_max_um=coat.get("dft_max_um"),
            )
        )
    await record_transition(db, ENTITY, job.id, None, job.status, user_id, None)
    await db.commit()
    return job


async def read_jobs(db: AsyncSession, jobs: list[CoatingJob]) -> list[dict[str, Any]]:
    systems = {j.system_id for j in jobs}
    codes = (
        dict(
            (await db.execute(select(CoatingSystem.id, CoatingSystem.code).where(CoatingSystem.id.in_(systems)))).tuples().all()
        )
        if systems
        else {}
    )
    nodes = {j.node_id for j in jobs}
    paths = (
        dict((await db.execute(select(AssetNode.id, AssetNode.display_path).where(AssetNode.id.in_(nodes)))).tuples().all())
        if nodes
        else {}
    )
    pending: dict[int, str] = {}
    if jobs:
        rows = await db.execute(
            select(CoatingStage.job_id, CoatingStage.name)
            .where(CoatingStage.job_id.in_([j.id for j in jobs]), CoatingStage.status != "passed")
            .order_by(CoatingStage.job_id, CoatingStage.seq)
        )
        for job_id, name in rows.tuples():
            pending.setdefault(job_id, name)
    return [
        JobRead.model_validate(j)
        .model_copy(
            update={
                "system_code": codes.get(j.system_id),
                "node_path": paths.get(j.node_id),
                "current_stage": pending.get(j.id),
            }
        )
        .model_dump(mode="json")
        for j in jobs
    ]


async def job_detail(db: AsyncSession, job: CoatingJob) -> dict[str, Any]:
    base = (await read_jobs(db, [job]))[0]
    system = await get_system(db, job.system_id)
    env = await db.execute(
        select(EnvironmentalReading).where(EnvironmentalReading.job_id == job.id).order_by(EnvironmentalReading.taken_at)
    )
    dft = await db.execute(select(DftSet).where(DftSet.job_id == job.id).order_by(DftSet.taken_at, DftSet.id))
    return {
        **base,
        "system": read_system(system),
        "stages": [StageRead.model_validate(s).model_dump(mode="json") for s in await stages_of(db, job.id)],
        "environment": [EnvironmentRead.model_validate(r).model_dump(mode="json") for r in env.scalars()],
        "dft_sets": [DftRead.model_validate(r).model_dump(mode="json") for r in dft.scalars()],
    }


async def _started(db: AsyncSession, job: CoatingJob, user_id: int) -> None:
    if job.status == "open":
        await record_transition(db, ENTITY, job.id, job.status, "in_progress", user_id, None)
        job.status = "in_progress"


async def add_environment(db: AsyncSession, job: CoatingJob, values: dict[str, Any], user_id: int) -> EnvironmentalReading:
    system = await get_system(db, job.system_id)
    if values.get("stage_id"):
        await get_stage(db, job, values["stage_id"])
    taken_at = values.get("taken_at") or utcnow()
    await assert_calibrated(db, job.project_id, values.get("equipment_ids") or [], taken_at.date())
    check = environment_check(
        values["surface_temp_c"],
        air_temp_c=values.get("air_temp_c"),
        rh_pct=values.get("rh_pct"),
        dew_point_c=values.get("dew_point_c"),
        required_margin_c=system.dew_point_margin_c,
    )
    failures = []
    if not check.passed:
        failures.append(
            f"surface {values['surface_temp_c']:g} °C is only {check.margin_c:g} °C above the dew point "
            f"{check.dew_point_c:g} °C (needs {check.required_margin_c:g} °C)"
        )
    rh = values.get("rh_pct")
    if rh is not None and system.max_rh_pct is not None and rh > system.max_rh_pct:
        failures.append(f"relative humidity {rh:g} % is above {system.max_rh_pct:g} %")
    reading = EnvironmentalReading(
        job_id=job.id,
        stage_id=values.get("stage_id"),
        taken_at=taken_at,
        air_temp_c=values.get("air_temp_c"),
        surface_temp_c=values["surface_temp_c"],
        rh_pct=rh,
        dew_point_c=check.dew_point_c,
        margin_c=check.margin_c,
        required_margin_c=check.required_margin_c,
        passed=not failures,
        failures=failures,
        equipment_ids=list(values.get("equipment_ids") or []),
        taken_by_id=user_id,
        note=values.get("note"),
    )
    db.add(reading)
    await _started(db, job, user_id)
    await db.commit()
    return reading


async def add_dft(db: AsyncSession, job: CoatingJob, values: dict[str, Any], user_id: int) -> DftSet:
    stage = await get_stage(db, job, values["stage_id"])
    if stage.kind != "coat" or stage.dft_min_um is None:
        raise NotACoat(stage.name)
    taken_at = values.get("taken_at") or utcnow()
    await assert_calibrated(db, job.project_id, values.get("equipment_ids") or [], taken_at.date())
    rule = values.get("rule")
    rule = str(rule.value if hasattr(rule, "value") else rule) if rule else job.dft_rule
    readings = [float(r) for r in values["readings"]]
    stats = dft_stats(readings, stage.dft_min_um, stage.dft_max_um, rule)
    row = DftSet(
        job_id=job.id,
        stage_id=stage.id,
        taken_at=taken_at,
        location=values.get("location"),
        readings=readings,
        rule=rule,
        dft_min_um=stage.dft_min_um,
        dft_max_um=stage.dft_max_um,
        count=stats.count,
        mean=stats.mean,
        minimum=stats.minimum,
        maximum=stats.maximum,
        pct_within=stats.pct_within,
        pct_below_min=stats.pct_below_min,
        passed=stats.passed,
        failures=list(stats.failures),
        equipment_ids=list(values.get("equipment_ids") or []),
        taken_by_id=user_id,
    )
    db.add(row)
    await _started(db, job, user_id)
    await db.commit()
    return row


async def release_problems(db: AsyncSession, job: CoatingJob, stage: CoatingStage) -> list[str]:
    """Why the hold point can't pass yet; empty when it can."""
    problems = []
    earlier = [s for s in await stages_of(db, job.id) if s.seq < stage.seq]
    if any(s.status != "passed" for s in earlier):
        problems.append("the previous hold point hasn't passed")
    env = list((await db.execute(select(EnvironmentalReading).where(EnvironmentalReading.stage_id == stage.id))).scalars())
    if not env:
        problems.append("no environmental reading recorded for this hold point")
    elif not all(r.passed for r in env):
        problems.append("an environmental reading failed (dew point / humidity)")
    if stage.kind == "coat":
        latest = await db.scalar(
            select(DftSet).where(DftSet.stage_id == stage.id).order_by(DftSet.taken_at.desc(), DftSet.id.desc()).limit(1)
        )
        if latest is None:
            problems.append("no DFT readings for this coat")
        elif not latest.passed:
            problems.append("the latest DFT set fails: " + "; ".join(latest.failures))
        if not stage.batch_numbers:
            problems.append("no product batch numbers recorded")
    else:
        system = await get_system(db, job.system_id)
        p = stage.measured_profile_um
        if system.profile_min_um is not None or system.profile_max_um is not None:
            if p is None:
                problems.append("no surface profile measured")
            elif (system.profile_min_um is not None and p < system.profile_min_um) or (
                system.profile_max_um is not None and p > system.profile_max_um
            ):
                problems.append(f"surface profile {p:g} µm is outside the specified range")
    return problems


async def release(db: AsyncSession, job: CoatingJob, stage: CoatingStage, result: str, note: str | None, user_id: int) -> None:
    if stage.status != "pending":
        raise HoldPointBlocked("already decided")
    if result == "passed":
        problems = await release_problems(db, job, stage)
        if problems:
            raise HoldPointBlocked("; ".join(problems))
    stage.status, stage.released_by_id, stage.released_at, stage.note = result, user_id, utcnow(), note or stage.note
    await record_transition(db, "coating_stage", stage.id, "pending", result, user_id, note)
    stages = await stages_of(db, job.id)
    target = job.status
    if result == "failed":
        target = "failed"
    elif all(s.status == "passed" for s in stages):
        target = "passed"
    elif job.status == "open":
        target = "in_progress"
    if target != job.status:
        await record_transition(db, ENTITY, job.id, job.status, target, user_id, note)
        job.status = target
    if job.created_by_id:
        await notify(
            db,
            [job.created_by_id],
            Category.STATUS,
            f"{job.code}: {stage.name} {result}",
            body=note,
            link=f"/coatings?project={job.project_id}&id={job.id}",
            entity=(ENTITY, job.id),
            actor_id=user_id,
        )
    await db.commit()
