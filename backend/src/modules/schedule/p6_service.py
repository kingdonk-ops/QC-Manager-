"""The P6 mirror (KERP p6-import-and-rsw-matching, adapted).

* **Idempotent on (project, P6 Activity ID).** Re-uploading the same file (same SHA-256) is a no-op.
* **Never deletes.** An activity missing from a new file becomes ``removed_from_schedule``; its links and
  all field work stay.
* **Preview before apply.** Upload stages the file and writes a change-impact report (``P6Change`` rows);
  the planner may exclude changes, then commits once.
* **Deterministic linking.** Name grammar + aliases + eligibility rules (``p6_rules``) link activities to the
  breakdown level with the ``schedule_link`` role; the rest go to the unmatched-row screen, where manual
  links can be remembered for later imports. Confirmed links are never moved by a re-import; a different
  parse raises a ``proposed`` link instead.
* **Schedule facts.** Total float and longest-path flags are kept as P6 owns them, for other modules' rules
  (``facts_for_node``); QC Manager never recomputes them from P6.
"""

import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ...infrastructure.records import record_transition
from ...infrastructure.tabular import write_table
from ..asset_tree import service as tree
from ..asset_tree.constants import Role
from ..asset_tree.models import AssetLevel, AssetNode
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from ..files.storage import storage
from ..inspections.models import Inspection
from ..projects.models import Project
from . import cpm, progress
from . import service as schedule
from .calendar import Calendar
from .interchange import Imported
from .models import Activity, Dependency, ScheduleSettings
from .p6_models import P6Change, P6Export, P6Import, P6Link, P6LinkMemory, P6Rule, ProgressVerification
from .p6_rules import (
    DEFAULT_RULES,
    FIELDS,
    LEVEL_VALUES,
    OPS,
    SOURCES,
    GrammarError,
    Parsed,
    RuleSet,
    build,
    compile_pattern,
    groups_for,
    link_info,
    norm,
)
from .p6_rules import eligible as is_eligible
from .p6_rules import parse as parse_name
from .schemas import ScheduleActivityStatus

ENTITY_IMPORT = "schedule_p6_import"
OWNED = (
    "name",
    "type",
    "task_type",
    "status_code",
    "planned_start",
    "planned_finish",
    "duration",
    "actual_start",
    "actual_finish",
    "percent_complete",
    "wbs",
    "codes",
    "udfs",
    "total_float_hours",
    "longest_path",
    "late_finish",
    "budget_hours",
)
"""P6-owned fields: the only ones an import ever writes."""
GROUPS: dict[str, tuple[str, ...]] = {
    "name_changed": ("name", "type"),
    "dates_changed": ("planned_start", "planned_finish", "duration", "late_finish"),
    "wbs_moved": ("wbs",),
    "status_changed": ("status_code", "actual_start", "actual_finish", "percent_complete"),
    "codes_or_udfs_changed": ("codes", "udfs"),
    "facts_changed": ("total_float_hours", "longest_path", "task_type", "budget_hours"),
}


class P6Error(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class ImportNotFound(ResourceNotFoundError):
    public_detail = "P6 import not found."


class ChangeNotFound(ResourceNotFoundError):
    public_detail = "Change not found."


class RuleNotFound(ResourceNotFoundError):
    public_detail = "P6 rule not found."


class LinkNotFound(ResourceNotFoundError):
    public_detail = "Link not found."


class ExportNotFound(ResourceNotFoundError):
    public_detail = "Export not found."


class VerificationNotFound(ResourceNotFoundError):
    public_detail = "Verification not found."


# --- settings and rules ----------------------------------------------------------------------------


async def settings_of(db: AsyncSession, project: Project) -> ScheduleSettings:
    return await schedule.get_settings(db, project)


async def rules_of(db: AsyncSession, project: Project) -> list[P6Rule]:
    """The project's rules, seeded once with the shipped defaults (deleting them afterwards sticks)."""
    settings = await settings_of(db, project)
    if not settings.p6_rules_seeded:
        for r in DEFAULT_RULES:
            db.add(P6Rule(project_id=project.id, **{"pattern": "", "source": "name", "params": {}, **r}))
        settings.p6_rules_seeded = True
        await db.flush()
    return list(
        (
            await db.execute(
                select(P6Rule).where(P6Rule.project_id == project.id).order_by(P6Rule.kind, P6Rule.sort_order, P6Rule.id)
            )
        ).scalars()
    )


def check_rule(kind: str, pattern: str, source: str, params: dict[str, Any]) -> None:
    try:
        if kind == "grammar":
            if source not in SOURCES:
                raise P6Error(f"Source must be one of {', '.join(SOURCES)}.")
            compile_pattern(pattern)
            if params.get("suffix", "separate") not in ("separate", "same") or params.get("window", "same") not in (
                "separate",
                "same",
            ):
                raise P6Error("suffix and window must be 'separate' or 'same'.")
            max_range = params.get("max_range", 50)
            if not isinstance(max_range, int) or isinstance(max_range, bool) or not 1 <= max_range <= 500:
                raise P6Error("max_range must be a whole number from 1 to 500.")
            if "list_separator" in params and (not isinstance(params["list_separator"], str) or not params["list_separator"]):
                raise P6Error("list_separator must be non-empty text.")
        elif kind == "eligibility":
            if params.get("field") not in FIELDS:
                raise P6Error(f"field must be one of {', '.join(FIELDS)}.")
            if params.get("op") not in OPS:
                raise P6Error(f"op must be one of {', '.join(OPS)}.")
            values = params.get("values")
            if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
                raise P6Error("values must be a non-empty list of text.")
            if params["op"] == "matches":
                for v in values:
                    re.compile(v)
        elif kind == "alias":
            if not pattern.strip() or not str(params.get("to") or "").strip():
                raise P6Error("An alias needs the spelling found in P6 (pattern) and params.to.")
        elif kind == "wbs_level":
            depth = params.get("depth")
            if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= 20:
                raise P6Error("params.depth must be a whole number from 1 (the first WBS level under the project) to 20.")
            if not isinstance(params.get("level"), str) or not params["level"].strip():
                raise P6Error("params.level must be the key of a breakdown level (e.g. site or area).")
            if params.get("value", "name") not in LEVEL_VALUES:
                raise P6Error("params.value must be 'name' or 'code'.")
    except GrammarError as exc:
        raise P6Error(str(exc)) from exc
    except re.error as exc:
        raise P6Error(f"Invalid regular expression: {exc}") from exc


async def create_rule(db: AsyncSession, project: Project, values: dict[str, Any]) -> P6Rule:
    await rules_of(db, project)
    check_rule(values["kind"], values.get("pattern", ""), values.get("source", "name"), values.get("params") or {})
    rule = P6Rule(project_id=project.id, **values)
    db.add(rule)
    await db.commit()
    return rule


async def get_rule(db: AsyncSession, project_id: int, rule_id: int) -> P6Rule:
    rule = await db.get(P6Rule, rule_id)
    if rule is None or rule.project_id != project_id:
        raise RuleNotFound(str(rule_id))
    return rule


async def update_rule(db: AsyncSession, rule: P6Rule, values: dict[str, Any]) -> P6Rule:
    pattern: str = values["pattern"] if values.get("pattern") is not None else rule.pattern
    source: str = values.get("source") or rule.source
    params: dict[str, Any] = values["params"] if values.get("params") is not None else rule.params
    check_rule(rule.kind, pattern, source, params)
    for key, value in values.items():
        if value is not None:
            setattr(rule, key, value)
    await db.commit()
    return rule


async def ruleset(db: AsyncSession, project: Project) -> RuleSet:
    return build(await rules_of(db, project))


# --- staging -------------------------------------------------------------------------------------


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def stage(parsed: Imported) -> dict[str, Any]:
    """The parsed file as plain JSON: WBS (by code path), activities (by P6 Activity ID) and relationships."""
    by_key = {a.key: a for a in parsed.activities}

    def wbs_path(key: str | None) -> str | None:
        codes: list[str] = []
        seen: set[str] = set()
        while key and key in by_key and key not in seen:
            seen.add(key)
            a = by_key[key]
            codes.append(a.code or a.name)
            key = a.parent_key
        return ".".join(reversed(codes)) if codes else None

    def wbs_chain(key: str | None) -> list[dict[str, str]]:
        """The WBS above an activity, top first: ``[{code, name}, ...]`` (used by ``wbs_level`` rules)."""
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        while key and key in by_key and key not in seen:
            seen.add(key)
            a = by_key[key]
            out.append({"code": a.code or "", "name": a.name or ""})
            key = a.parent_key
        return list(reversed(out))

    wbs, rows, warnings = [], [], []
    ids: dict[str, str] = {}
    for n, a in enumerate(parsed.activities):
        if a.type == "summary":
            path = wbs_path(a.key) or a.key
            parent = wbs_path(a.parent_key)
            wbs.append(
                {
                    "p6_id": f"WBS:{path}"[:60],
                    "name": a.name,
                    "parent": f"WBS:{parent}"[:60] if parent else None,
                    "outline": a.wbs_code or str(n + 1),
                    "order": n,
                }
            )
            ids[a.key] = f"WBS:{path}"[:60]
            continue
        pid = (a.code or a.key)[:60]
        if pid in ids.values():
            warnings.append(f"Activity ID {pid} appears twice; the second one was skipped.")
            continue
        ids[a.key] = pid
        parent_path = wbs_path(a.parent_key)
        extra = a.extra or {}
        row = {
            "p6_id": pid,
            "guid": extra.get("guid"),
            "name": a.name,
            "type": a.type,
            "task_type": extra.get("task_type") or ("TT_Mile" if a.type == "milestone" else "TT_Task"),
            "status_code": extra.get("status_code")
            or ("TK_Complete" if a.actual_finish else "TK_Active" if a.actual_start else "TK_NotStart"),
            "planned_start": _iso(a.planned_start),
            "planned_finish": _iso(a.planned_finish),
            "duration": a.duration,
            "actual_start": _iso(a.actual_start),
            "actual_finish": _iso(a.actual_finish),
            "percent_complete": a.percent_complete,
            "wbs": f"WBS:{parent_path}"[:60] if parent_path else None,
            "wbs_path": parent_path,
            "codes": extra.get("codes") or {},
            "udfs": extra.get("udfs") or {},
            "total_float_hours": extra.get("total_float_hours"),
            "longest_path": bool(extra.get("longest_path")),
            "late_finish": extra.get("late_finish"),
            "budget_hours": a.budget_hours,
            "outline": a.wbs_code or str(n + 1),
            "order": n,
        }
        row["hash"] = row_hash(row)
        # Not P6-owned fields (outside the hash): context for linking and for showing P6's float in days.
        row["wbs_chain"] = wbs_chain(a.parent_key)
        row["day_hours"] = extra.get("day_hours")
        rows.append(row)
    links = [
        {"pred": ids[lk.predecessor], "succ": ids[lk.successor], "type": lk.type, "lag": lk.lag}
        for lk in parsed.links
        if lk.predecessor in ids and lk.successor in ids
    ]
    return {
        "wbs": wbs,
        "activities": rows,
        "links": links,
        "warnings": warnings,
        "calendar": {"working_days": parsed.working_days, "holidays": [h.isoformat() for h in parsed.holidays]},
    }


def row_hash(row: dict[str, Any]) -> str:
    owned = {k: row.get(k) for k in OWNED}
    return hashlib.sha256(json.dumps(owned, sort_keys=True, default=str).encode()).hexdigest()


# --- change-impact report ------------------------------------------------------------------------


@dataclass
class Existing:
    id: int
    p6_id: str
    guid: str | None
    state: str
    src: dict[str, Any]
    links: list[str] = field(default_factory=list)


def _days_between(a: Any, b: Any) -> int | None:
    if not a or not b:
        return None
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def diff(
    rows: list[dict[str, Any]], existing: dict[str, Existing], legacy: dict[str, int]
) -> tuple[list[dict[str, Any]], Counter]:
    """What committing ``rows`` would change against the mirror. Pure: no database."""
    source_ids = {r["p6_id"] for r in rows}
    by_guid = {e.guid: e for e in existing.values() if e.guid and e.p6_id not in source_ids}
    changes: list[dict[str, Any]] = []
    counts: Counter = Counter()
    seen: set[str] = set()

    def add(row: dict[str, Any], kind: str, activity_id: int | None, old: dict, new: dict, impact: dict | None = None) -> None:
        changes.append(
            {
                "p6_activity_id": row["p6_id"],
                "name": row["name"][:300],
                "change_type": kind,
                "activity_id": activity_id,
                "old": old,
                "new": new,
                "impact": impact or {},
            }
        )
        counts[kind] += 1

    for row in rows:
        pid = row["p6_id"]
        ex = existing.get(pid)
        if ex is None and row.get("guid") and row["guid"] in by_guid:
            ex = by_guid.pop(row["guid"])
            add(row, "renumbered", ex.id, {"p6_activity_id": ex.p6_id}, {"p6_activity_id": pid}, {"linked_nodes": ex.links})
        if ex is None:
            owned = {k: row.get(k) for k in OWNED}
            if pid in legacy:
                add(row, "adopted", legacy[pid], {}, {"p6_activity_id": pid, "guid": row.get("guid"), **owned})
            else:
                add(row, "new", None, {}, {"p6_activity_id": pid, "guid": row.get("guid"), **owned})
            continue
        seen.add(ex.p6_id)
        if ex.src.get("hash") == row["hash"] and ex.state == "active":
            counts["unchanged"] += 1
            continue
        if ex.state != "active":
            add(row, "restored", ex.id, {"schedule_state": ex.state}, {"schedule_state": "active"}, {"linked_nodes": ex.links})
        for kind, fields in GROUPS.items():
            old = {f: ex.src.get(f) for f in fields}
            new = {f: row.get(f) for f in fields}
            if old == new:
                continue
            impact: dict[str, Any] = {"linked_nodes": ex.links} if ex.links else {}
            if kind == "dates_changed":
                impact["start_shift_days"] = _days_between(old["planned_start"], new["planned_start"])
                impact["finish_shift_days"] = _days_between(old["planned_finish"], new["planned_finish"])
            if kind == "codes_or_udfs_changed":
                notes = [f"{k}: {v}" for k, v in (row.get("udfs") or {}).items() if "chang" in str(v).lower()]
                if notes:
                    impact["udf_notes"] = notes
            add(row, kind, ex.id, old, new, impact)
    for ex in existing.values():
        if ex.p6_id not in seen and ex.state == "active" and ex.guid not in {r.get("guid") for r in rows if r.get("guid")}:
            add(
                {"p6_id": ex.p6_id, "name": ex.src.get("name") or ex.p6_id},
                "removed",
                ex.id,
                {"schedule_state": "active"},
                {"schedule_state": "removed_from_schedule"},
                {"linked_nodes": ex.links},
            )
    return changes, counts


async def mirror(db: AsyncSession, project_id: int) -> tuple[dict[str, Existing], dict[str, int]]:
    """Mirrored task activities by P6 Activity ID, and legacy-imported activities (``task:`` external id) by code."""
    acts = list(
        (await db.execute(select(Activity).where(Activity.project_id == project_id, Activity.type != "summary"))).scalars()
    )
    paths = await link_paths(db, [a.id for a in acts if a.p6_activity_id])
    existing = {
        a.p6_activity_id: Existing(
            a.id, a.p6_activity_id, a.p6_guid, a.schedule_state, dict(a.p6_facts.get("src") or {}), paths.get(a.id, [])
        )
        for a in acts
        if a.p6_activity_id
    }
    legacy = {a.code: a.id for a in acts if not a.p6_activity_id and (a.external_id or "").startswith("task:")}
    return existing, legacy


async def link_paths(db: AsyncSession, activity_ids: list[int]) -> dict[int, list[str]]:
    if not activity_ids:
        return {}
    rows = await db.execute(
        select(P6Link.activity_id, AssetNode.display_path)
        .join(AssetNode, AssetNode.id == P6Link.node_id)
        .where(P6Link.activity_id.in_(activity_ids), P6Link.status == "confirmed")
    )
    out: dict[int, list[str]] = defaultdict(list)
    for aid, path in rows.all():
        out[aid].append(path)
    return out


# --- resolving names onto the breakdown ----------------------------------------------------------


@dataclass
class Ref:
    id: int
    level_key: str
    code: str
    path: str
    display: str


@dataclass
class Resolution:
    status: str  # matched | create | unmatched
    node: Ref | None = None
    progress: Ref | None = None
    reason: str | None = None


Creator = Callable[[AssetLevel, str, Ref | None], Awaitable[Ref]]


class Resolver:
    """Finds (or plans) the nodes a parsed name addresses, top level first, each under the one above."""

    def __init__(self, levels: list[AssetLevel], nodes: list[AssetNode], create_under: Ref | None, allow_create: bool) -> None:
        self.levels = sorted(levels, key=lambda lv: (lv.depth, lv.id))
        self.create_under = create_under
        self.allow_create = allow_create
        self.index: dict[tuple[str, str], list[Ref]] = defaultdict(list)
        for n in nodes:
            if n.status == "active":
                self.add(Ref(n.id, n.level_key, norm(n.code), n.path, n.display_path))

    def add(self, ref: Ref) -> None:
        self.index[(ref.level_key, ref.code)].append(ref)

    def _values(self, groups: dict[str, str]) -> list[tuple[AssetLevel, str, bool]]:
        out = []
        for lv in self.levels:
            roles = lv.roles or []
            value = groups.get(lv.key)
            optional = False
            if value is None and Role.WORK_ANCHOR.value in roles:
                value = groups.get("anchor_code")
            if value is None and Role.PHYSICAL.value in roles:
                value = groups.get("asset")
            if (
                value is None
                and Role.PROGRESS_UNIT.value in roles
                and Role.WORK_ANCHOR.value not in roles
                and Role.SCHEDULE_LINK.value not in roles
            ):
                value, optional = groups.get("activity_type"), True
            if value:
                out.append((lv, value, optional))
        return out

    async def resolve(self, groups: dict[str, str], creator: Creator) -> Resolution:
        values = self._values(groups)
        if not values:
            return Resolution("unmatched", reason="Nothing parsed from the name maps to a breakdown level.")
        parent: Ref | None = None
        resolved: list[tuple[AssetLevel, Ref, bool]] = []
        planned = False
        for lv, value, optional in values:
            cands = [r for r in self.index.get((lv.key, norm(value)), []) if parent is None or r.path.startswith(parent.path)]
            if len(cands) > 1:
                if optional:
                    continue
                return Resolution("unmatched", reason=f"{lv.label} '{value}' is ambiguous: {len(cands)} nodes have that code.")
            if cands:
                parent = cands[0]
                planned = planned or parent.id < 0  # planned earlier in this preview
                resolved.append((lv, parent, optional))
                continue
            under = parent or self.create_under
            allowed = lv.allowed_parent_keys or []
            reason = None
            if not self.allow_create:
                reason = f"{lv.label} '{value}' not found."
            elif under is None and allowed and "" not in allowed:
                reason = f"{lv.label} '{value}' not found; choose where new {lv.label_plural.lower()} are created."
            elif under is not None and under.level_key not in allowed:
                reason = f"{lv.label} '{value}' not found and a {lv.label} can't be created under a {under.level_key}."
            if reason:
                if optional:
                    continue
                return Resolution("unmatched", reason=reason)
            try:
                ref = await creator(lv, value, under)
            except tree.TreeRuleError as exc:
                if optional:
                    continue
                return Resolution("unmatched", reason=str(exc.public_detail))
            self.add(ref)
            parent, planned = ref, True
            resolved.append((lv, ref, optional))
        link = next((r for lv, r, _ in reversed(resolved) if Role.SCHEDULE_LINK.value in (lv.roles or [])), None)
        if link is None:
            return Resolution("unmatched", reason="No breakdown level with the schedule-link role was matched.")
        prog = next((r for lv, r, opt in reversed(resolved) if opt), None)
        return Resolution("create" if planned else "matched", node=link, progress=prog)


async def resolver_for(db: AsyncSession, project_id: int, options: dict[str, Any]) -> Resolver:
    levels = list((await db.execute(select(AssetLevel).where(AssetLevel.project_id == project_id))).scalars())
    nodes = list((await db.execute(select(AssetNode).where(AssetNode.project_id == project_id))).scalars())
    under = None
    if options.get("create_under_node_id"):
        n = next((x for x in nodes if x.id == options["create_under_node_id"]), None)
        if n is not None:
            under = Ref(n.id, n.level_key, norm(n.code), n.path, n.display_path)
    return Resolver(levels, nodes, under, bool(options.get("create_missing")))


def preview_creator() -> Creator:
    counter = iter(range(1, 10**9))

    async def create(lv: AssetLevel, value: str, under: Ref | None) -> Ref:
        n = next(counter)
        path = f"{under.path if under else '/'}-{n}/"
        display = f"{under.display} / {value}" if under else value
        return Ref(-n, lv.key, norm(value), path, display)

    return create


def real_creator(db: AsyncSession, project_id: int, p6_id: Callable[[], str]) -> Creator:
    async def create(lv: AssetLevel, value: str, under: Ref | None) -> Ref:
        if under is not None and under.id < 0:
            raise tree.TreeRuleError("Parent wasn't created.")
        node = await tree.create_node(
            db,
            project_id,
            {
                "level_key": lv.key,
                "code": value[:120],
                "parent_id": under.id if under else None,
                "external_source": "p6",
                "external_id": p6_id()[:120],
            },
        )
        return Ref(node.id, node.level_key, norm(node.code), node.path, node.display_path)

    return create


# --- imports -------------------------------------------------------------------------------------


async def get_import(db: AsyncSession, project_id: int, import_id: int) -> P6Import:
    imp = await db.get(P6Import, import_id)
    if imp is None or imp.project_id != project_id:
        raise ImportNotFound(str(import_id))
    return imp


async def _store_original(db: AsyncSession, project: Project, imp: P6Import, data: bytes, actor_id: int) -> None:
    upload = UploadFile(io.BytesIO(data), filename=imp.file_name)
    key, size, digest = await storage().save(upload, len(data) + 1)
    stored = StoredFile(
        name=imp.file_name,
        content_type="application/octet-stream",
        size=size,
        sha256=digest,
        storage_key=key,
        uploaded_by_id=actor_id,
        project_id=project.id,
        entity_type=ENTITY_IMPORT,
        entity_id=imp.id,
        category="other",
        tags=["p6"],
    )
    db.add(stored)
    await db.flush()
    imp.file_id = stored.id


async def create_import(
    db: AsyncSession, project: Project, data: bytes, file_name: str, parsed: Imported, options: dict[str, Any], actor_id: int
) -> tuple[P6Import, bool]:
    """Stage the file and write its change-impact report. The same file twice returns the first import."""
    sha = hashlib.sha256(data).hexdigest()
    earlier = await db.scalar(
        select(P6Import)
        .where(P6Import.project_id == project.id, P6Import.sha256 == sha, P6Import.status.in_(("previewed", "committed")))
        .order_by(P6Import.id.desc())
    )
    if earlier is not None:
        return earlier, True
    if await db.scalar(select(P6Import.id).where(P6Import.project_id == project.id, P6Import.status == "previewed")):
        raise P6Error("Another import is waiting for review. Commit or discard it first.")
    staged = stage(parsed)
    imp = P6Import(
        project_id=project.id,
        file_name=file_name[:300],
        sha256=sha,
        format=parsed.format,
        source_project=(parsed.project_name or "")[:200] or None,
        data_date=parsed.data_date,
        status="previewed",
        staging=staged,
        options=options,
        created_by_id=actor_id,
    )
    db.add(imp)
    await db.flush()
    await _store_original(db, project, imp, data, actor_id)

    existing, legacy = await mirror(db, project.id)
    changes, counts = diff(staged["activities"], existing, legacy)

    # Matching preview: what linking would do on commit.
    rules = await ruleset(db, project)
    resolver = await resolver_for(db, project.id, options)
    creator = preview_creator()
    current_links = await _links_by_activity(db, [e.id for e in existing.values()])
    match_counts: Counter = Counter()
    match: dict[str, dict[str, Any]] = {}
    for row in staged["activities"]:
        if row["type"] == "summary":
            continue
        parsed_name = parse_name(row, rules)
        ok, why = is_eligible(row, parsed_name, rules)
        if not ok:
            match_counts["ineligible"] += 1
            match[row["p6_id"]] = {"status": "ineligible", "reason": why}
            continue
        if parsed_name.groups is None:
            match_counts["unmatched"] += 1
            match[row["p6_id"]] = {"status": "unmatched", "reason": "No grammar matched the name."}
            continue
        results = [await resolver.resolve(g, creator) for g in groups_for(parsed_name)]
        res = next((r for r in results if r.node is None), None)
        res = res or next((r for r in results if r.status == "create"), results[0])
        match_counts[res.status] += 1
        match[row["p6_id"]] = {
            "status": res.status,
            "reason": res.reason,
            "node": res.node.display if res.node else None,
            "groups": parsed_name.groups,
        }
        if len(results) > 1:
            match[row["p6_id"]]["nodes"] = [r.node.display for r in results if r.node]
        if parsed_name.qualifier:
            match[row["p6_id"]]["qualifier"] = parsed_name.qualifier
        ex = existing.get(row["p6_id"])
        if ex and current_links.get(ex.id) and any(r.node and r.node.id not in current_links[ex.id] for r in results):
            match[row["p6_id"]]["relink_proposed"] = True
    for ch in changes:
        m = match.get(ch["p6_activity_id"])
        if ch["change_type"] == "name_changed" and m and m.get("relink_proposed"):
            ch["impact"]["relink_proposed"] = m.get("node")
        db.add(P6Change(import_id=imp.id, **ch))

    shifts = [
        ch["impact"].get("finish_shift_days") or 0
        for ch in changes
        if ch["change_type"] == "dates_changed" and ch["impact"].get("finish_shift_days")
    ]
    imp.summary = {
        "activities": len(staged["activities"]),
        "wbs": len(staged["wbs"]),
        "relationships": len(staged["links"]),
        "changes": dict(counts),
        "matching": dict(match_counts),
        "date_shifts": {"count": len(shifts), "max_slip_days": max(shifts, default=0), "max_gain_days": min(shifts, default=0)},
        "warnings": staged["warnings"],
    }
    imp.staging = {**staged, "match": match}
    await record_transition(db, ENTITY_IMPORT, imp.id, None, "previewed", actor_id)
    await db.commit()
    return imp, False


async def get_change(db: AsyncSession, imp: P6Import, change_id: int) -> P6Change:
    ch = await db.get(P6Change, change_id)
    if ch is None or ch.import_id != imp.id:
        raise ChangeNotFound(str(change_id))
    return ch


async def set_excluded(db: AsyncSession, imp: P6Import, ch: P6Change, excluded: bool) -> P6Change:
    if imp.status != "previewed":
        raise P6Error("Only an import waiting for review can be changed.")
    ch.excluded = excluded
    await db.commit()
    return ch


async def discard(db: AsyncSession, imp: P6Import, actor_id: int) -> None:
    if imp.status != "previewed":
        raise P6Error("Only an import waiting for review can be discarded.")
    imp.status = "discarded"
    await record_transition(db, ENTITY_IMPORT, imp.id, "previewed", "discarded", actor_id)
    await db.commit()


def _status_of(src: dict[str, Any]) -> str:
    if src.get("actual_finish") or (src.get("percent_complete") or 0) >= 100 or src.get("status_code") == "TK_Complete":
        return ScheduleActivityStatus.COMPLETED
    if src.get("actual_start") or (src.get("percent_complete") or 0) > 0 or src.get("status_code") == "TK_Active":
        return ScheduleActivityStatus.IN_PROGRESS
    return ScheduleActivityStatus.PENDING


def _apply(act: Activity, src: dict[str, Any], wbs_acts: dict[str, Activity]) -> None:
    """Write the P6-owned fields of ``src`` onto the activity (and nothing else)."""
    act.name = (src.get("name") or act.name)[:300]
    if src.get("type") in ("task", "milestone"):
        act.type = src["type"]
    for f in ("planned_start", "planned_finish", "actual_start", "actual_finish"):
        setattr(act, f, date.fromisoformat(src[f]) if src.get(f) else None)
    act.duration = 0 if act.type == "milestone" else max(0, int(src.get("duration") or 0))
    act.percent_complete = min(max(float(src.get("percent_complete") or 0), 0.0), 100.0)
    act.budget_hours = Decimal(str(round(float(src.get("budget_hours") or 0), 2)))
    parent = wbs_acts.get(src.get("wbs") or "")
    act.parent_id = parent.id if parent else None
    act.status = _status_of(src)
    if act.status == ScheduleActivityStatus.COMPLETED and act.actual_finish is None:
        act.actual_finish, act.actual_start = act.planned_finish, act.actual_start or act.planned_start
    if act.actual_start is None and act.planned_start is not None:
        act.constraint_type, act.constraint_date = "snet", act.planned_start
    else:
        act.constraint_type, act.constraint_date = "asap", None


async def _sync_wbs(db: AsyncSession, project_id: int, wbs: list[dict[str, Any]]) -> dict[str, Activity]:
    """Create or rename the WBS summaries; never delete one."""
    found = {
        a.p6_activity_id: a
        for a in (
            await db.execute(select(Activity).where(Activity.project_id == project_id, Activity.p6_activity_id.like("WBS:%")))
        ).scalars()
        if a.p6_activity_id
    }
    for w in wbs:
        a = found.get(w["p6_id"])
        if a is None:
            a = Activity(
                project_id=project_id,
                code=w["p6_id"].split(".")[-1].removeprefix("WBS:")[:40],
                wbs_code=w["outline"][:60],
                name=w["name"][:300],
                type="summary",
                p6_activity_id=w["p6_id"],
            )
            db.add(a)
            found[w["p6_id"]] = a
        a.name, a.wbs_code, a.sort_order, a.schedule_state = w["name"][:300], w["outline"][:60], w["order"], "active"
    await db.flush()
    for w in wbs:
        parent = found.get(w["parent"] or "")
        found[w["p6_id"]].parent_id = parent.id if parent else None
    return found


async def _links_by_activity(db: AsyncSession, activity_ids: list[int]) -> dict[int, set[int]]:
    if not activity_ids:
        return {}
    out: dict[int, set[int]] = defaultdict(set)
    for aid, nid in (
        await db.execute(select(P6Link.activity_id, P6Link.node_id).where(P6Link.activity_id.in_(activity_ids)))
    ).all():
        out[aid].add(nid)
    return out


async def _sync_dependencies(db: AsyncSession, project_id: int, links: list[dict[str, Any]], acts: dict[str, Activity]) -> None:
    """P6 relationships between mirrored activities follow the file; links to hand-made activities stay."""
    ids = {a.id for a in acts.values()}
    wanted: dict[tuple[int, int], tuple[str, int]] = {}
    for lk in links:
        p, s = acts.get(lk["pred"]), acts.get(lk["succ"])
        if p is not None and s is not None and p.id != s.id:
            wanted[(p.id, s.id)] = (lk["type"], int(lk["lag"]))
    current = {
        (d.predecessor_id, d.successor_id): d
        for d in (await db.execute(select(Dependency).where(Dependency.project_id == project_id))).scalars()
        if d.predecessor_id in ids and d.successor_id in ids
    }
    for pair, d in current.items():
        if pair not in wanted:
            await db.delete(d)
        else:
            d.type, d.lag = wanted[pair]
    for pair, (kind, lag) in wanted.items():
        if pair not in current:
            db.add(Dependency(project_id=project_id, predecessor_id=pair[0], successor_id=pair[1], type=kind, lag=lag))
    await db.flush()


async def commit(db: AsyncSession, project: Project, imp: P6Import, actor_id: int) -> P6Import:
    """Apply every change not excluded, link by grammar, and recalculate, in one transaction."""
    if imp.status != "previewed":
        raise P6Error("Only an import waiting for review can be committed.")
    staged = imp.staging
    rows = {r["p6_id"]: r for r in staged["activities"]}
    changes = list((await db.execute(select(P6Change).where(P6Change.import_id == imp.id).order_by(P6Change.id))).scalars())
    wbs_acts = await _sync_wbs(db, project.id, staged.get("wbs", []))

    acts: dict[str, Activity] = {
        a.p6_activity_id: a
        for a in (
            await db.execute(select(Activity).where(Activity.project_id == project.id, Activity.p6_activity_id.is_not(None)))
        ).scalars()
        if a.p6_activity_id and not a.p6_activity_id.startswith("WBS:")
    }
    by_id = {a.id: a for a in acts.values()}
    applied: Counter[str] = Counter()
    excluded_rows: set[str] = set()
    for ch in changes:
        row = rows.get(ch.p6_activity_id)
        if ch.excluded:
            excluded_rows.add(ch.p6_activity_id)
            continue
        applied[ch.change_type] += 1
        if ch.change_type in ("new", "adopted"):
            assert row is not None
            act = by_id.get(ch.activity_id or 0) or (await db.get(Activity, ch.activity_id) if ch.activity_id else None)
            if act is None:
                act = Activity(
                    project_id=project.id, code=row["p6_id"][:40], wbs_code=row["outline"][:60], name=row["name"][:300]
                )
                db.add(act)
            act.p6_activity_id, act.p6_guid, act.schedule_state = row["p6_id"], row.get("guid"), "active"
            act.p6_facts = {**(act.p6_facts or {}), "src": {**{k: row.get(k) for k in OWNED}, "hash": row["hash"]}}
            _apply(act, act.p6_facts["src"], wbs_acts)
            await db.flush()
            acts[row["p6_id"]], by_id[act.id] = act, act
            ch.activity_id = act.id
            continue
        act = by_id.get(ch.activity_id or 0)
        if act is None:
            continue
        if ch.change_type == "renumbered":
            acts.pop(act.p6_activity_id or "", None)
            act.p6_activity_id = ch.new["p6_activity_id"]
            act.code = act.p6_activity_id[:40]
            acts[act.p6_activity_id] = act
        elif ch.change_type in ("removed", "restored"):
            act.schedule_state = ch.new["schedule_state"]
        else:
            src = dict(act.p6_facts.get("src") or {})
            src.update({k: v for k, v in ch.new.items() if k in OWNED})
            src["hash"] = row_hash(src)
            act.p6_facts = {**act.p6_facts, "src": src}
            _apply(act, src, wbs_acts)
    # Rows whose changes were all applied carry the source hash exactly, so they read unchanged next time.
    for pid, row in rows.items():
        act = acts.get(pid)
        if act is None:
            continue
        act.wbs_code, act.sort_order = row["outline"][:60], row["order"]
        if row.get("day_hours") and (act.p6_facts or {}).get("day_hours") != row["day_hours"]:
            act.p6_facts = {**(act.p6_facts or {}), "day_hours": row["day_hours"]}
        if pid not in excluded_rows and act.p6_facts.get("src"):
            act.p6_facts = {**act.p6_facts, "src": {**{k: row.get(k) for k in OWNED}, "hash": row["hash"]}}
    await db.flush()

    await _sync_dependencies(db, project.id, staged.get("links", []), acts)
    settings = await settings_of(db, project)
    if imp.data_date:
        settings.data_date = imp.data_date
    cal = staged.get("calendar") or {}
    if cal.get("working_days"):
        settings.working_days, settings.holidays = cal["working_days"], cal.get("holidays", [])
    starts = [a.planned_start for a in acts.values() if a.planned_start]
    if starts and (settings.start_date is None or min(starts) < settings.start_date):
        settings.start_date = min(starts)

    linking = await link_by_grammar(db, project, imp, acts, rows, actor_id)
    rollup = await refresh_p6_nodes(db, project.id, imp.id)

    warnings = list(imp.summary.get("warnings", []))
    try:
        await schedule.recalculate(db, project)
    except cpm.CycleError:
        warnings.append("The file's relationships loop, so dates weren't recalculated; P6's dates are shown.")
    imp.summary = {**imp.summary, "applied": dict(applied), "linking": linking, "warnings": warnings, "node_rollup": rollup}
    imp.status, imp.committed_by_id, imp.committed_at = "committed", actor_id, datetime.now(UTC)
    await record_transition(db, ENTITY_IMPORT, imp.id, "previewed", "committed", actor_id)
    await db.commit()
    await publish(
        "schedule.p6.import.committed",
        {"project_id": project.id, "import_id": imp.id, "applied": dict(applied), "by": actor_id},
    )
    return imp


async def link_by_grammar(
    db: AsyncSession, project: Project, imp: P6Import, acts: dict[str, Activity], rows: dict[str, dict[str, Any]], actor_id: int
) -> dict[str, int]:
    """Link every eligible, active, mirrored activity of the file: grammar first, then remembered links.

    Activities that already have a link keep it; a parse naming a different node adds a ``proposed`` link.
    """
    rules = await ruleset(db, project)
    resolver = await resolver_for(db, project.id, imp.options)
    current: dict[str, str] = {}
    creator = real_creator(db, project.id, lambda: current["id"])
    links = await _links_by_activity(db, [a.id for a in acts.values()])
    memory = {
        m.key: m.node_id
        for m in (await db.execute(select(P6LinkMemory).where(P6LinkMemory.project_id == project.id))).scalars()
    }
    counts: Counter = Counter()
    for pid, row in rows.items():
        act = acts.get(pid)
        if act is None or act.schedule_state != "active" or row["type"] == "summary":
            continue
        current["id"] = pid
        parsed: Parsed = parse_name(row, rules)
        ok, why = is_eligible(row, parsed, rules)
        facts = dict(act.p6_facts or {})
        facts["eligible"] = ok
        facts["groups"] = parsed.groups
        if not ok:
            facts["match"] = {"status": "ineligible", "reason": why}
            act.p6_facts = facts
            counts["ineligible"] += 1
            continue
        results = [await resolver.resolve(g, creator) for g in groups_for(parsed)] or [
            Resolution("unmatched", reason="No grammar matched the name.")
        ]
        failed = next((r for r in results if r.node is None), None)
        res = failed or results[0]
        have = links.get(act.id, set())
        if failed is None:
            nodes = [r for r in results if r.node is not None]
            facts["match"] = {
                "status": "matched",
                "node": nodes[0].node.display if nodes[0].node else None,
                "rule": parsed.rule,
                **({"nodes": [r.node.display for r in nodes if r.node]} if len(nodes) > 1 else {}),
            }
            created = sum(1 for r in nodes if r.status == "create")
            if created:
                counts["nodes_created"] += created
            info = link_info(parsed)
            # A first link is confirmed; a re-import naming a different node only proposes it (never moves one).
            first_time = not have
            new_nodes = [r.node for r in nodes if r.node is not None and r.node.id not in have]
            for node in new_nodes:
                db.add(
                    P6Link(
                        project_id=project.id,
                        activity_id=act.id,
                        node_id=node.id,
                        progress_node_id=next((r.progress.id for r in nodes if r.node is node and r.progress), None),
                        work_window=parsed.window,
                        method="name_grammar",
                        status="confirmed" if first_time else "proposed",
                        parsed=info,
                        created_by_id=actor_id,
                    )
                )
                have = have | {node.id}
            if new_nodes:
                counts["linked" if first_time else "proposed"] += 1
            else:
                counts["already_linked"] += 1
            links[act.id] = have
        else:
            facts["match"] = {"status": "unmatched", "reason": res.reason, "rule": parsed.rule}
            remembered = memory.get(norm(act.name))
            if not have and remembered:
                db.add(
                    P6Link(
                        project_id=project.id,
                        activity_id=act.id,
                        node_id=remembered,
                        method="remembered",
                        status="confirmed",
                        created_by_id=actor_id,
                    )
                )
                links[act.id] = {remembered}
                facts["match"] = {"status": "remembered", "reason": res.reason}
                counts["remembered"] += 1
            elif have:
                counts["already_linked"] += 1
            else:
                counts["unmatched"] += 1
        act.p6_facts = facts
    await db.flush()
    return dict(counts)


async def refresh_p6_nodes(db: AsyncSession, project_id: int, import_id: int) -> dict[str, dict[str, Any]]:
    """Name and date the breakdown nodes P6 created from the activities linked to them.

    Only nodes with ``external_source = "p6"`` are touched. A work anchor (RSW) is named after the activity
    types of its activities (``SCA Erect, B, P``; the RSW number stays its code); every linked node gets the
    earliest planned start, latest planned finish and the activities' budget hours (an activity linked to
    several RSWs shares its hours evenly). A value someone has changed since the last import is left alone:
    a field is only written while it is empty or still holds what the previous import put there.
    """
    previous = await db.scalar(
        select(P6Import)
        .where(P6Import.project_id == project_id, P6Import.status == "committed", P6Import.id != import_id)
        .order_by(P6Import.id.desc())
        .limit(1)
    )
    before: dict[str, dict[str, Any]] = (previous.summary.get("node_rollup") or {}) if previous else {}
    anchor_levels = {
        lv.key
        for lv in (await db.execute(select(AssetLevel).where(AssetLevel.project_id == project_id))).scalars()
        if Role.WORK_ANCHOR.value in (lv.roles or [])
    }
    rows = (
        await db.execute(
            select(P6Link.node_id, Activity)
            .join(Activity, Activity.id == P6Link.activity_id)
            .join(AssetNode, AssetNode.id == P6Link.node_id)
            .where(
                P6Link.project_id == project_id,
                P6Link.status == "confirmed",
                AssetNode.external_source == "p6",
                Activity.schedule_state == "active",
            )
        )
    ).all()
    by_node: dict[int, list[Activity]] = defaultdict(list)
    shares: Counter[int] = Counter()
    for node_id, act in rows:
        by_node[node_id].append(act)
        shares[act.id] += 1
    rollup: dict[str, dict[str, Any]] = {}
    for node_id, acts in by_node.items():
        node = await db.get(AssetNode, node_id)
        if node is None or node.status != "active":
            continue
        acts.sort(key=lambda a: (a.planned_start or date.max, a.code))
        starts = [a.planned_start for a in acts if a.planned_start]
        finishes = [a.planned_finish for a in acts if a.planned_finish]
        hours = sum((Decimal(a.budget_hours or 0) / shares[a.id] for a in acts), Decimal(0)).quantize(Decimal("0.01"))
        values: dict[str, Any] = {
            "planned_start": min(starts).isoformat() if starts else None,
            "planned_finish": max(finishes).isoformat() if finishes else None,
            "budget_hours": str(hours) if hours else None,
        }
        if node.level_key in anchor_levels:
            types: list[str] = []
            for a in acts:
                t = ((a.p6_facts or {}).get("groups") or {}).get("activity_type")
                if t and t not in types:
                    types.append(t)
            values["name"] = ", ".join(types)[:300] or None
        old = before.get(str(node_id), {})
        current = {
            "planned_start": node.planned_start.isoformat() if node.planned_start else None,
            "planned_finish": node.planned_finish.isoformat() if node.planned_finish else None,
            "budget_hours": (
                str(Decimal(node.budget_hours).quantize(Decimal("0.01"))) if node.budget_hours is not None else None
            ),
            "name": node.name,
        }
        for key, value in values.items():
            if current[key] is not None and current[key] != old.get(key):
                continue  # changed by someone since the last import
            if key in ("planned_start", "planned_finish"):
                setattr(node, key, date.fromisoformat(value) if value else None)
            elif key == "budget_hours":
                node.budget_hours = Decimal(value) if value else None
            else:
                node.name = value
        rollup[str(node_id)] = values
    await db.flush()
    return rollup


# --- for planning --------------------------------------------------------------------------------


async def programme_for_planning(
    db: AsyncSession,
    project_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    search: str | None = None,
    activity_ids: list[int] | None = None,
    limit: int = 1000,
    window: tuple[date, date] | None = None,
) -> list[dict[str, Any]]:
    """Mirrored P6 activities with the work anchors they are linked to, for the planner to pick from.

    Active, non-summary activities whose planned dates overlap ``start``..``end`` (or exactly ``activity_ids``),
    optionally filtered by ``search`` over the Activity ID, the name and the activity codes. Each carries its
    confirmed links (``anchors``) with the note the name gave (``OHP``, ``Access``...), its activity type and
    its P6 dates and hours. Activities without a link are returned too, with ``anchors = []``.

    With ``window`` (a plan's start and end) each row also carries ``window_share``, the part of the activity's
    working days on the project calendar that falls inside the window, and ``hours_in_window``, its hours times
    that share. A long activity planned in a three-week look-ahead then brings three weeks of hours, not all of
    them. The P6 mirror itself never changes.
    """
    q = select(Activity).where(
        Activity.project_id == project_id,
        Activity.p6_activity_id.is_not(None),
        Activity.type != "summary",
        Activity.schedule_state == "active",
    )
    if activity_ids is not None:
        q = q.where(Activity.id.in_(activity_ids or [-1]))
    else:
        if start is not None:
            q = q.where((Activity.planned_finish.is_(None)) | (Activity.planned_finish >= start))
        if end is not None:
            q = q.where((Activity.planned_start.is_(None)) | (Activity.planned_start <= end))
    acts = list((await db.execute(q.order_by(Activity.planned_start, Activity.code))).scalars())
    if search:
        needle = search.strip().lower()
        acts = [
            a
            for a in acts
            if needle in (a.p6_activity_id or "").lower()
            or needle in a.name.lower()
            or any(needle in str(v).lower() for v in ((a.p6_facts or {}).get("src") or {}).get("codes", {}).values())
        ]
    acts = acts[:limit]
    links = list(
        (
            await db.execute(
                select(P6Link, AssetNode)
                .join(AssetNode, AssetNode.id == P6Link.node_id)
                .where(P6Link.activity_id.in_([a.id for a in acts] or [-1]), P6Link.status == "confirmed")
                .order_by(AssetNode.path)
            )
        ).all()
    )
    anchors: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for link, node in links:
        anchors[link.activity_id].append(
            {
                "node_id": node.id,
                "code": node.code,
                "name": node.name,
                "display_path": node.display_path,
                "qualifier": (link.parsed or {}).get("qualifier"),
                "work_window": link.work_window,
            }
        )
    cal = None
    if window is not None:
        settings = await db.get(ScheduleSettings, project_id)
        cal = schedule.calendar_of(settings) if settings else Calendar(window[0])
    out = []
    for a in acts:
        facts = a.p6_facts or {}
        src = facts.get("src") or {}
        share = window_share(cal, a.planned_start, a.planned_finish, window) if cal and window else None
        out.append(
            {
                "activity_id": a.id,
                "p6_activity_id": a.p6_activity_id,
                "name": a.name,
                "planned_start": a.planned_start,
                "planned_finish": a.planned_finish,
                "budget_hours": a.budget_hours,
                "status": a.status,
                "activity_type": (facts.get("groups") or {}).get("activity_type"),
                "codes": src.get("codes") or {},
                "anchors": anchors.get(a.id, []),
                "window_share": round(share, 4) if share is not None else None,
                "hours_in_window": (
                    (Decimal(a.budget_hours or 0) * Decimal(str(share))).quantize(Decimal("0.01"))
                    if share is not None
                    else None
                ),
            }
        )
    return out


def window_share(cal: Calendar, start: date | None, finish: date | None, window: tuple[date, date]) -> float:
    """The part of an activity's working days that falls inside ``window`` (0..1, exact).

    Undated activities count as wholly inside. An activity with no working days in its span (all on days off)
    is shared by calendar days instead, so nothing is ever divided by zero.
    """
    if start is None or finish is None:
        return 1.0
    finish = max(finish, start)
    lo, hi = max(start, window[0]), min(finish, window[1])
    if hi < lo:
        return 0.0
    total = cal.working_days_between(start, finish)
    if total == 0:
        return ((hi - lo).days + 1) / ((finish - start).days + 1)
    return min(cal.working_days_between(lo, hi) / total, 1.0)


# --- links ---------------------------------------------------------------------------------------


async def read_links(db: AsyncSession, links: list[P6Link]) -> list[dict[str, Any]]:
    acts = (
        {a.id: a for a in (await db.execute(select(Activity).where(Activity.id.in_({x.activity_id for x in links})))).scalars()}
        if links
        else {}
    )
    nodes = (
        {
            n.id: n.display_path
            for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_({x.node_id for x in links})))).scalars()
        }
        if links
        else {}
    )
    return [
        {
            "id": x.id,
            "project_id": x.project_id,
            "activity_id": x.activity_id,
            "p6_activity_id": acts[x.activity_id].p6_activity_id if x.activity_id in acts else None,
            "activity_name": acts[x.activity_id].name if x.activity_id in acts else "",
            "node_id": x.node_id,
            "node_path": nodes.get(x.node_id, ""),
            "progress_node_id": x.progress_node_id,
            "work_window": x.work_window,
            "method": x.method,
            "status": x.status,
            "parsed": x.parsed,
            "created_at": x.created_at,
        }
        for x in links
    ]


async def get_link(db: AsyncSession, project_id: int, link_id: int) -> P6Link:
    link = await db.get(P6Link, link_id)
    if link is None or link.project_id != project_id:
        raise LinkNotFound(str(link_id))
    return link


async def link_manually(
    db: AsyncSession, project: Project, act: Activity, node_id: int, window: str | None, remember: bool, actor_id: int
) -> P6Link:
    """Link an activity to a node by hand; existing links stay. ``remember`` applies it to later imports."""
    if act.project_id != project.id:
        raise schedule.ActivityNotFoundError(str(act.id))
    node = await tree.get_node(db, node_id, project.id)
    link = await db.scalar(select(P6Link).where(P6Link.activity_id == act.id, P6Link.node_id == node.id))
    if link is None:
        link = P6Link(
            project_id=project.id,
            activity_id=act.id,
            node_id=node.id,
            work_window=window,
            method="manual",
            status="confirmed",
            created_by_id=actor_id,
        )
        db.add(link)
    else:
        link.status, link.method = "confirmed", "manual"
    if remember:
        key = norm(act.name)[:300]
        mem = await db.scalar(select(P6LinkMemory).where(P6LinkMemory.project_id == project.id, P6LinkMemory.key == key))
        if mem is None:
            db.add(P6LinkMemory(project_id=project.id, key=key, node_id=node.id, created_by_id=actor_id))
        else:
            mem.node_id = node.id
    await db.commit()
    return link


async def confirm_link(db: AsyncSession, link: P6Link) -> P6Link:
    link.status = "confirmed"
    await db.commit()
    return link


async def unmatched(db: AsyncSession, project_id: int, page_offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    """Eligible, active, mirrored activities with no confirmed link."""
    confirmed = select(P6Link.activity_id).where(P6Link.project_id == project_id, P6Link.status == "confirmed")
    where = [
        Activity.project_id == project_id,
        Activity.p6_activity_id.is_not(None),
        Activity.type != "summary",
        Activity.schedule_state == "active",
        Activity.id.not_in(confirmed),
    ]
    acts = [
        a
        for a in (await db.execute(select(Activity).where(*where).order_by(Activity.wbs_code, Activity.id))).scalars()
        if a.p6_facts.get("eligible", True)
    ]
    page = acts[page_offset : page_offset + limit]
    proposed = (
        list(
            (
                await db.execute(
                    select(P6Link).where(P6Link.activity_id.in_([a.id for a in page]), P6Link.status == "proposed")
                )
            ).scalars()
        )
        if page
        else []
    )
    read = await read_links(db, proposed)
    out = []
    for a in page:
        src = a.p6_facts.get("src") or {}
        match = a.p6_facts.get("match") or {}
        out.append(
            {
                "id": a.id,
                "p6_activity_id": a.p6_activity_id,
                "name": a.name,
                "wbs_path": (src.get("wbs") or "").removeprefix("WBS:") or None,
                "planned_start": a.planned_start,
                "planned_finish": a.planned_finish,
                "reason": match.get("reason"),
                "groups": a.p6_facts.get("groups"),
                "proposed": [r for r in read if r["activity_id"] == a.id],
            }
        )
    return out, len(acts)


# --- rule testing --------------------------------------------------------------------------------


async def test_rules(db: AsyncSession, project: Project, body: dict[str, Any]) -> list[dict[str, Any]]:
    rows = await rules_of(db, project)
    rules = build(rows)
    if body.get("pattern"):
        check_rule("grammar", body["pattern"], body.get("source", "name"), body.get("params") or {})
        trial = P6Rule(
            project_id=project.id,
            kind="grammar",
            name="Pattern under test",
            pattern=body["pattern"],
            source=body.get("source", "name"),
            params=body.get("params") or {},
        )
        trial.id = None  # type: ignore[assignment]
        rules.grammars = build([trial]).grammars
    resolver = await resolver_for(db, project.id, {})
    out = []
    for s in body["samples"]:
        row = {
            "p6_id": s.get("code") or "",
            "name": s["name"],
            "wbs_path": s.get("wbs") or "",
            "task_type": s.get("task_type") or "TT_Task",
        }
        parsed = parse_name(row, rules)
        ok, why = is_eligible(row, parsed, rules)
        result = {
            "sample": s["name"],
            "matched_rule": parsed.rule,
            "groups": parsed.groups,
            "window": parsed.window,
            "anchors": parsed.anchors,
            "qualifier": parsed.qualifier,
            "eligible": ok,
            "ineligible_reason": why,
            "resolution": "ineligible" if not ok else "unmatched",
            "node_id": None,
            "node_path": None,
            "reason": None if parsed.groups is not None else "No grammar matched.",
        }
        if ok and parsed.groups is not None:
            res = await resolver.resolve(parsed.groups, preview_creator())
            result.update(
                resolution=res.status,
                node_id=res.node.id if res.node and res.node.id > 0 else None,
                node_path=res.node.display if res.node else None,
                reason=res.reason,
            )
        out.append(result)
    return out


# --- schedule facts ------------------------------------------------------------------------------


async def facts_for_node(db: AsyncSession, project: Project, node_id: int) -> dict[str, Any]:
    """P6 float and critical-path facts of the activities linked to the node, its ancestors or its subtree.

    Several activities: the minimum float, and critical if any is. As of the last committed import.
    """
    node = await tree.get_node(db, node_id, project.id)
    ids = set(tree.path_ids(node)) | set(await tree.subtree_ids(db, node.id, with_lineage=False))
    settings = await settings_of(db, project)
    rows = (
        await db.execute(
            select(Activity).where(
                Activity.id.in_(select(P6Link.activity_id).where(P6Link.node_id.in_(ids), P6Link.status == "confirmed")),
                Activity.schedule_state == "active",
            )
        )
    ).scalars()
    acts = []
    for a in rows:
        src = a.p6_facts.get("src") or {}
        tf = src.get("total_float_hours")
        if settings.p6_critical_definition == "longest_path":
            critical = bool(src.get("longest_path"))
        else:
            critical = tf is not None and float(tf) <= settings.p6_critical_float_hours
        acts.append(
            {
                "activity_id": a.id,
                "p6_activity_id": a.p6_activity_id,
                "name": a.name,
                "total_float_hours": tf,
                "longest_path": bool(src.get("longest_path")),
                "late_finish": src.get("late_finish"),
                "on_critical_path": critical,
            }
        )
    floats = [float(a["total_float_hours"]) for a in acts if a["total_float_hours"] is not None]
    basis = (
        "longest path flag"
        if settings.p6_critical_definition == "longest_path"
        else f"total float ≤ {settings.p6_critical_float_hours:g} h"
    )
    return {
        "node_id": node.id,
        "data_date": settings.data_date,
        "critical_definition": settings.p6_critical_definition,
        "critical_float_hours": settings.p6_critical_float_hours,
        "total_float_hours": min(floats) if floats else None,
        "on_critical_path": any(a["on_critical_path"] for a in acts),
        "critical_basis": basis,
        "activities": acts,
    }


# --- verified progress ---------------------------------------------------------------------------


async def add_verification(db: AsyncSession, project: Project, values: dict[str, Any], actor_id: int) -> ProgressVerification:
    node = await tree.get_node(db, values["node_id"], project.id)
    if not await tree.has_role(db, node, Role.PROGRESS_UNIT):
        raise P6Error("Verified quantities are recorded on progress-unit nodes.")
    if values.get("inspection_id"):
        insp = await db.get(Inspection, values["inspection_id"])
        if insp is None or insp.project_id != project.id:
            raise P6Error("That inspection isn't in this project.")
    v = ProgressVerification(
        project_id=project.id,
        node_id=node.id,
        verified_qty=values["verified_qty"],
        verified_on=values.get("verified_on") or date.today(),
        inspection_id=values.get("inspection_id"),
        verified_by_id=actor_id,
        note=values.get("note"),
    )
    db.add(v)
    await db.commit()
    await publish("schedule.progress.verified", {"project_id": project.id, "node_id": node.id, "verification_id": v.id})
    return v


async def read_verifications(db: AsyncSession, rows: list[ProgressVerification]) -> list[dict[str, Any]]:
    if not rows:
        return []
    nodes = {
        n.id: n.display_path
        for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_({r.node_id for r in rows})))).scalars()
    }
    insp = {
        i.id: i
        for i in (
            await db.execute(select(Inspection).where(Inspection.id.in_({r.inspection_id for r in rows if r.inspection_id})))
        ).scalars()
    }
    out = []
    for r in rows:
        i = insp.get(r.inspection_id or 0)
        counts = r.inspection_id is None or (i is not None and i.status in progress.PASSED and (i.failed or 0) == 0)
        out.append(
            {
                "id": r.id,
                "project_id": r.project_id,
                "node_id": r.node_id,
                "node_path": nodes.get(r.node_id, ""),
                "verified_qty": r.verified_qty,
                "verified_on": r.verified_on,
                "inspection_id": r.inspection_id,
                "inspection_code": i.code if i else None,
                "counts": counts,
                "verified_by_id": r.verified_by_id,
                "note": r.note,
            }
        )
    return out


async def get_verification(db: AsyncSession, project_id: int, vid: int) -> ProgressVerification:
    v = await db.get(ProgressVerification, vid)
    if v is None or v.project_id != project_id:
        raise VerificationNotFound(str(vid))
    return v


# --- actuals export ------------------------------------------------------------------------------


async def progress_rows(db: AsyncSession, project: Project) -> list[dict[str, Any]]:
    """Verified progress of every linked, active, mirrored activity, as P6 should hear it."""
    links = list(
        (
            await db.execute(
                select(P6Link)
                .join(Activity, Activity.id == P6Link.activity_id)
                .where(P6Link.project_id == project.id, P6Link.status == "confirmed", Activity.schedule_state == "active")
            )
        ).scalars()
    )
    by_act: dict[int, set[int]] = defaultdict(set)
    for x in links:
        by_act[x.activity_id].add(x.progress_node_id or x.node_id)
    if not by_act:
        return []
    acts = {
        a.id: a
        for a in (await db.execute(select(Activity).where(Activity.id.in_(by_act)).order_by(Activity.wbs_code))).scalars()
    }
    targets = {n for ns in by_act.values() for n in ns}
    units = await progress.under(db, project.id, targets)
    quantities = await progress.node_quantities(db, project.id)
    paths = {n.id: n.display_path for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(targets)))).scalars()}
    out = []
    for aid in sorted(by_act, key=lambda i: (schedule.wbs_key(acts[i].wbs_code), i)):
        a = acts[aid]
        mine = {u for n in by_act[aid] for u in units.get(n, set())}
        r = progress.rollup([quantities[u] for u in sorted(mine) if u in quantities])
        src = a.p6_facts.get("src") or {}
        verified = r.verified_percent
        code = (
            "TK_Complete"
            if verified is not None and verified >= 100 and r.actual_finish
            else "TK_Active"
            if verified
            else "TK_NotStart"
        )
        out.append(
            {
                "activity_id": a.id,
                "p6_activity_id": a.p6_activity_id,
                "name": a.name,
                "nodes": sorted(paths.get(n, "") for n in by_act[aid]),
                "units": r.units,
                "p6_status": src.get("status_code"),
                "p6_percent": src.get("percent_complete"),
                "reported_percent": r.reported_percent,
                "verified_percent": verified,
                "actual_start": r.actual_start,
                "actual_finish": r.actual_finish if code == "TK_Complete" else None,
                "status_code": code,
            }
        )
    return out


def _differs(r: dict[str, Any]) -> bool:
    if r["verified_percent"] is None:
        return False
    return abs(float(r["p6_percent"] or 0) - float(r["verified_percent"])) >= 0.05 or (r["status_code"] or "") != (
        r["p6_status"] or ""
    )


async def create_export(db: AsyncSession, project: Project, fmt: str, only_changed: bool, actor_id: int) -> P6Export:
    rows = [r for r in await progress_rows(db, project) if r["verified_percent"] is not None]
    if only_changed:
        rows = [r for r in rows if _differs(r)]
    plain = [
        {
            "p6_activity_id": r["p6_activity_id"],
            "name": r["name"],
            "status_code": r["status_code"],
            "verified_percent": r["verified_percent"],
            "actual_start": _iso(r["actual_start"]),
            "actual_finish": _iso(r["actual_finish"]),
        }
        for r in rows
    ]
    exp = P6Export(
        project_id=project.id, format=fmt, data_date=date.today(), rows=plain, row_count=len(plain), created_by_id=actor_id
    )
    db.add(exp)
    await db.commit()
    await publish("schedule.p6.exported", {"project_id": project.id, "export_id": exp.id, "rows": len(plain)})
    return exp


async def get_export(db: AsyncSession, project_id: int, export_id: int) -> P6Export:
    exp = await db.get(P6Export, export_id)
    if exp is None or exp.project_id != project_id:
        raise ExportNotFound(str(export_id))
    return exp


XER_STATUS_TEXT = {"TK_NotStart": "Not Started", "TK_Active": "In Progress", "TK_Complete": "Completed"}
CSV_COLUMNS = [
    ("p6_activity_id", "Activity ID"),
    ("name", "Activity Name"),
    ("status", "Activity Status"),
    ("actual_start", "Actual Start"),
    ("actual_finish", "Actual Finish"),
    ("verified_percent", "Physical % Complete"),
]


def _xer_date(value: str | None) -> str:
    return f"{value} 08:00" if value else ""


def render_export(exp: P6Export, project: Project) -> tuple[bytes, str, str]:
    """XER (TASK update keyed on task_code), P6 XML (Activity by Id) or CSV with P6's column names."""
    if exp.format == "xer":
        clean = lambda v: str(v if v is not None else "").replace("\t", " ").replace("\n", " ")  # noqa: E731
        lines = [
            "\t".join(
                [
                    "ERMHDR",
                    "19.12",
                    exp.data_date.isoformat(),
                    "Project",
                    "QC Manager",
                    "QCManager",
                    "Project Management",
                    project.currency,
                ]
            ),
            "%T\tPROJECT",
            "%F\tproj_short_name\tlast_recalc_date",
            f"%R\t{clean(project.code)}\t{exp.data_date.isoformat()} 00:00",
            "%T\tTASK",
            "%F\ttask_code\ttask_name\tstatus_code\tact_start_date\tact_end_date\tphys_complete_pct\tcomplete_pct_type",
        ]
        for r in exp.rows:
            lines.append(
                "\t".join(
                    [
                        "%R",
                        clean(r["p6_activity_id"]),
                        clean(r["name"]),
                        r["status_code"],
                        _xer_date(r["actual_start"]),
                        _xer_date(r["actual_finish"]),
                        f"{float(r['verified_percent'] or 0):g}",
                        "CP_Phys",
                    ]
                )
            )
        lines.append("%E")
        return ("\r\n".join(lines) + "\r\n").encode("cp1252", errors="replace"), "text/plain", "xer"
    if exp.format == "p6_xml":
        ns = "http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects"
        root = ET.Element("APIBusinessObjects", {"xmlns": ns})
        proj = ET.SubElement(root, "Project")
        ET.SubElement(proj, "Id").text = project.code
        ET.SubElement(proj, "DataDate").text = f"{exp.data_date.isoformat()}T00:00:00"
        for r in exp.rows:
            a = ET.SubElement(proj, "Activity")
            ET.SubElement(a, "Id").text = r["p6_activity_id"]
            ET.SubElement(a, "Name").text = r["name"]
            ET.SubElement(a, "Status").text = XER_STATUS_TEXT.get(r["status_code"], "Not Started")
            ET.SubElement(a, "PercentCompleteType").text = "Physical"
            ET.SubElement(a, "PhysicalPercentComplete").text = f"{float(r['verified_percent'] or 0):g}"
            if r["actual_start"]:
                ET.SubElement(a, "ActualStartDate").text = f"{r['actual_start']}T08:00:00"
            if r["actual_finish"]:
                ET.SubElement(a, "ActualFinishDate").text = f"{r['actual_finish']}T17:00:00"
        return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8"), "application/xml", "xml"
    rows = [{**r, "status": XER_STATUS_TEXT.get(r["status_code"], "")} for r in exp.rows]
    return write_table(CSV_COLUMNS, rows, "csv", title="P6 actuals")


async def count_imports(db: AsyncSession, project_id: int) -> int:
    return await db.scalar(select(func.count()).select_from(P6Import).where(P6Import.project_id == project_id)) or 0
