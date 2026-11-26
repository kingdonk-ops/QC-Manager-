"""Seed one project from a P6 programme, then fill it with sample field data tied to that programme.

    uv run python -m scripts.seed_p6_project            # local
    SEED_DATA=true  (docker-compose.coolify.yml runs it once per deploy as the ``seed`` service)

Runs only when ``SEED_DATA`` is ``true``, so it does nothing on a deploy unless switched on. Every step is
safe to repeat: a step whose output already exists is skipped, so a redeploy never duplicates anything.

1. The project ``SEED_PROJECT_CODE`` (default ``P6-DEMO``) is created if missing, with the remediation
   hierarchy (site > area > asset > RSW) and rules that turn P6 WBS levels into sites and areas.
2. The programme is imported, from the XER at ``SEED_P6_XER`` (default ``/app/data/files/seed/programme.xer``,
   on the shared ``files`` volume), unless the project already has a committed P6 import, for example one
   uploaded through Schedule > Import. With neither, the script stops here and the next run carries on.
3. Sample records are generated against the imported RSWs: two plans built from the programme, scaffolds
   at several stages, tasks, an ITP applied to RSWs, inspections, NCRs and RFIs. All of them are marked
   ``[sample]`` in their notes or description, so they are easy to find and remove.

The programme file is real project data, so it is never committed to the repository.
"""

import asyncio
import logging
import os
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.registry import import_models
from src.infrastructure.database.session import local_session
from src.modules.asset_tree.models import AssetLevel, AssetNode
from src.modules.asset_tree.packs import apply_pack
from src.modules.inspections import itp
from src.modules.inspections import service as inspections
from src.modules.inspections.schemas import ChecklistTemplateIn
from src.modules.ncr.service import create_ncr
from src.modules.planner import service as planner
from src.modules.projects.models import Project
from src.modules.projects.service import add_member
from src.modules.rfi.service import create_rfi
from src.modules.scaffolds import service as scaffolds
from src.modules.scaffolds.models import Scaffold
from src.modules.schedule import p6_service as p6
from src.modules.schedule.interchange import parse
from src.modules.schedule.p6_models import P6Import, P6Rule
from src.modules.tasks.service import create_task
from src.modules.user.models import User

logger = logging.getLogger("seed_p6_project")

MARK = "[sample]"
PACK = "remediation-rsw"
ALL: frozenset[str] = frozenset()  # the actor is a superuser, so no permission set is needed


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


async def _actor(db: AsyncSession) -> dict[str, Any]:
    username = _env("ADMIN_USERNAME", "admin")
    user = await db.scalar(select(User).where(User.username == username))
    if user is None:
        user = await db.scalar(select(User).where(User.is_superuser.is_(True)).order_by(User.id))
    if user is None:
        raise SystemExit("seed: no administrator exists yet; the bootstrap service creates one first")
    return {"id": user.id, "name": user.name, "username": user.username, "is_superuser": user.is_superuser}


async def _project(db: AsyncSession, actor: dict[str, Any]) -> Project:
    code = _env("SEED_PROJECT_CODE", "P6-DEMO")
    project = await db.scalar(select(Project).where(Project.code == code))
    if project is None:
        project = Project(code=code, name=_env("SEED_PROJECT_NAME", "P6 programme (sample data)"))
        project.description = f"{MARK} Seeded from a P6 programme with generated field records."
        db.add(project)
        await db.flush()
        logger.info("seed: created project %s", code)
    await add_member(db, project.id, actor["id"], "direct", actor["id"])
    await db.commit()

    levels = await db.scalar(select(func.count()).select_from(AssetLevel).where(AssetLevel.project_id == project.id))
    if not levels:
        await apply_pack(db, project.id, PACK)
        logger.info("seed: applied the %s hierarchy", PACK)

    has_rules = await db.scalar(
        select(func.count()).select_from(P6Rule).where(P6Rule.project_id == project.id, P6Rule.kind == "wbs_level")
    )
    if not has_rules:
        site, area = int(_env("SEED_P6_WBS_SITE_DEPTH", "3")), int(_env("SEED_P6_WBS_AREA_DEPTH", "4"))
        await p6.create_rule(
            db, project, {"kind": "wbs_level", "name": "WBS site level", "params": {"depth": site, "level": "site"}}
        )
        await p6.create_rule(
            db, project, {"kind": "wbs_level", "name": "WBS area level", "params": {"depth": area, "level": "area"}}
        )
        logger.info("seed: WBS level %s becomes a site, level %s an area", site, area)
    return project


async def _programme(db: AsyncSession, project: Project, actor: dict[str, Any]) -> P6Import | None:
    done = await db.scalar(
        select(P6Import).where(P6Import.project_id == project.id, P6Import.status == "committed").order_by(P6Import.id.desc())
    )
    if done is not None:
        logger.info("seed: programme already imported (%s)", done.file_name)
        return done

    path = Path(_env("SEED_P6_XER", "/app/data/files/seed/programme.xer"))
    if not path.is_file():
        logger.warning("seed: no programme yet. Put the XER at %s or import it under Schedule > Import, then redeploy", path)
        return None

    data = path.read_bytes()
    imp, reused = await p6.create_import(db, project, data, path.name, parse(data), {"create_missing": True}, actor["id"])
    if imp.status == "previewed":
        await p6.commit(db, project, imp, actor["id"])
    logger.info("seed: imported %s (%s)", path.name, (imp.summary or {}).get("matching"))
    return imp


def _rows_by_node(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        for anchor in row["anchors"]:
            out.setdefault(anchor["node_id"], []).append(row)
    return out


async def _plan_start(db: AsyncSession, project: Project) -> date:
    """The Monday of this week, moved into the span of the linked programme if today falls outside it."""
    rows = await p6.programme_for_planning(db, project.id, limit=100_000)
    starts = sorted(r["planned_start"] for r in rows if r["anchors"] and r["planned_start"])
    day = date.today()
    if starts:
        day = min(max(day, starts[0]), starts[-1])
    return day - timedelta(days=day.weekday())


async def _plans(db: AsyncSession, project: Project, start: date, actor: dict[str, Any]) -> list[dict[str, Any]]:
    windows = [
        ("Two-week look-ahead", "look_ahead", start, start + timedelta(days=13), 40),
        ("Shutdown campaign", "shutdown", start + timedelta(days=21), start + timedelta(days=48), 60),
    ]
    rows: list[dict[str, Any]] = []
    for title, kind, s, e, cap in windows:
        found = await p6.programme_for_planning(db, project.id, start=s, end=e, window=(s, e))
        linked = [r for r in found if r["anchors"]][:cap]
        rows += linked
        plan = await planner.create_plan(
            db,
            {
                "project_id": project.id,
                "title": f"{title} ({s:%d %b})",
                "window_start": s,
                "window_end": e,
                "kind": kind,
                "owner_id": actor["id"],
                "notes": f"{MARK} Built from the imported programme.",
            },
            actor["id"],
        )
        result = await planner.add_from_programme(db, plan, [r["activity_id"] for r in linked], "rsw", actor["id"])
        await db.commit()
        logger.info("seed: plan '%s' with %s packs", plan.title, result["packs_created"])
    return rows


async def _scaffolds(db: AsyncSession, project: Project, nodes: list[AssetNode], actor: dict[str, Any]) -> int:
    stages = [
        ["approved"],
        ["approved", "erecting"],
        ["approved", "erecting", "erected", "green"],
        ["approved", "erecting", "erected", "green"],
        ["approved", "erecting", "erected", "yellow"],
        ["approved", "erecting", "erected", "green", "dismantle_requested"],
        [],
    ]
    for i, node in enumerate(nodes):
        s = await scaffolds.create_scaffold(
            db,
            {
                "project_id": project.id,
                "node_id": node.id,
                "purpose": f"Access for insulation works at {node.display_path}",
                "scaffold_type": random.choice(["independent", "tower", "birdcage"]),
                "required_by": date.today() + timedelta(days=random.randint(2, 30)),
                "location_text": node.display_path,
                "notes": MARK,
            },
            actor,
        )
        for step in stages[i % len(stages)]:
            if step in {"green", "yellow"}:
                await scaffolds.inspect(db, s, {"kind": "handover", "tag": step, "tag_no": f"T-{s.id:04d}"}, actor)
                await db.commit()
            else:
                await scaffolds.transition(db, s, step, actor, ALL)
    return len(nodes)


async def _itp(db: AsyncSession, project: Project, nodes: list[AssetNode], actor: dict[str, Any]) -> int:
    values = ChecklistTemplateIn(
        project_id=project.id,
        name="Hot insulation ITP (sample)",
        kind="itp",
        trade="Insulation",
        description=MARK,
        activities=[
            {
                "title": "Surface preparation and pre-insulation inspection",
                "verifying_document": "ITR-01",
                "points": {"contractor": "H", "client": "W"},
            },
            {
                "title": "Insulation thickness and fixing",
                "verifying_document": "ITR-02",
                "points": {"contractor": "W", "client": "R"},
            },
            {
                "title": "Cladding, sealing and banding",
                "verifying_document": "ITR-03",
                "points": {"contractor": "W", "client": "S"},
            },
            {
                "title": "Final walk-down and handover",
                "verifying_document": "ITR-04",
                "points": {"contractor": "H", "client": "H"},
            },
        ],
    ).model_dump(mode="json")
    template = await inspections.create_template(db, values, actor["id"])
    for node in nodes:
        await itp.instantiate(db, template, node.id, None, actor["id"])
    await db.commit()
    return len(nodes)


async def _inspections(db: AsyncSession, project: Project, nodes: list[AssetNode], actor: dict[str, Any]) -> int:
    values = ChecklistTemplateIn(
        project_id=project.id,
        name="Daily insulation walk-down (sample)",
        description=MARK,
        sections=[
            {
                "title": "Workfront",
                "items": [{"text": "Permit and isolation in place"}, {"text": "Access scaffold tagged green"}],
            },
            {
                "title": "Workmanship",
                "items": [{"text": "No gaps or wet insulation"}, {"text": "Cladding overlaps shed water"}],
            },
        ],
    ).model_dump(mode="json")
    template = await inspections.create_template(db, values, actor["id"])
    for i, node in enumerate(nodes):
        await inspections.create_inspection(
            db,
            template,
            {
                "title": f"Walk-down {node.code}",
                "location": node.display_path,
                "inspector_id": actor["id"],
                "scheduled_date": date.today() + timedelta(days=i % 10),
                "notes": MARK,
                "location_node_id": node.id,
            },
            actor["id"],
        )
    await db.commit()
    return len(nodes)


TASKS = [
    ("Confirm isolation for {code}", "construction", "high"),
    ("Order cladding for {code}", "procurement", "medium"),
    ("Walk down {code} with the client", "general", "medium"),
    ("Close out punch items on {code}", "construction", "low"),
    ("Check insulation spec for {code}", "design", "medium"),
]
NCRS = [
    ("Wet insulation found under cladding", "major"),
    ("Banding spacing exceeds specification", "minor"),
    ("Damaged jacketing at support", "minor"),
]
RFIS = [
    ("Insulation thickness at flanges", "Drawing shows 50 mm but the line class calls for 75 mm. Which applies?"),
    ("Removable boxes on valves", "Are removable insulation boxes required on the control valves in this area?"),
    ("Paint before insulation", "Is a coating required on carbon steel before insulating at this RSW?"),
]


async def _registers(db: AsyncSession, project: Project, nodes: list[AssetNode], actor: dict[str, Any]) -> None:
    statuses = ["todo", "todo", "in_progress", "review", "done"]
    for i, node in enumerate(nodes):
        title, kind, priority = TASKS[i % len(TASKS)]
        await create_task(
            db,
            project_id=project.id,
            title=title.format(code=node.code),
            created_by_id=actor["id"],
            entity=("asset_node", node.id),
            description=f"{MARK} {node.display_path}",
            type=kind,
            priority=priority,
            status=statuses[i % len(statuses)],
            assignee_id=actor["id"],
            due_date=date.today() + timedelta(days=3 + i),
        )
    for i, node in enumerate(nodes[: len(NCRS) * 2]):
        title, severity = NCRS[i % len(NCRS)]
        await create_ncr(
            db,
            project_id=project.id,
            title=f"{title} ({node.code})",
            raised_by_id=actor["id"],
            description=MARK,
            severity=severity,
            location=node.display_path,
            anchor_node_id=node.id,
            due_date=date.today() + timedelta(days=7),
        )
    for node, (subject, question) in zip(nodes, RFIS, strict=False):
        await create_rfi(
            db,
            {
                "project_id": project.id,
                "subject": f"{subject} ({node.code})",
                "question": f"{question}\n\n{MARK}",
                "location": node.display_path,
                "status": "open",
            },
            actor,
        )


async def _samples(db: AsyncSession, project: Project, imp: P6Import, actor: dict[str, Any]) -> None:
    seeded = await db.scalar(
        select(func.count()).select_from(Scaffold).where(Scaffold.project_id == project.id, Scaffold.notes.like(f"{MARK}%"))
    )
    if seeded:
        logger.info("seed: sample records already exist; nothing to add")
        return

    random.seed(int(_env("SEED_RANDOM", "42")))
    start = await _plan_start(db, project)
    rows = await _plans(db, project, start, actor)
    by_node = _rows_by_node(rows)
    nodes = list((await db.scalars(select(AssetNode).where(AssetNode.id.in_(list(by_node))).order_by(AssetNode.id))).all())
    if not nodes:
        rsw = select(AssetNode).where(AssetNode.project_id == project.id, AssetNode.level_key == "rsw")
        nodes = list((await db.scalars(rsw.order_by(AssetNode.id).limit(60))).all())
    if not nodes:
        logger.warning("seed: the programme linked no RSWs, so there is nothing to hang sample records on")
        return

    scaffold_nodes = [n for n in nodes if any("sca" in (r["activity_type"] or "").lower() for r in by_node.get(n.id, []))]
    counts = {
        "scaffolds": await _scaffolds(db, project, (scaffold_nodes or nodes)[:21], actor),
        "itps": await _itp(db, project, nodes[:15], actor),
        "inspections": await _inspections(db, project, nodes[:12], actor),
    }
    await _registers(db, project, nodes[:25], actor)
    await db.commit()
    logger.info("seed: sample records added %s, plus tasks, NCRs and RFIs", counts)


async def main() -> None:
    if _env("SEED_DATA", "false").lower() != "true":
        logger.info("seed: SEED_DATA is not true; skipping")
        return
    import_models()
    async with local_session() as db:
        actor = await _actor(db)
        project = await _project(db, actor)
        imp = await _programme(db, project, actor)
        if imp is not None:
            await _samples(db, project, imp, actor)
    logger.info("seed: done")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(main())
