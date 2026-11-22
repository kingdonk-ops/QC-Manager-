"""The ingestion wizard: a spreadsheet of breakdown rows → nodes (and optionally items), driven by a mapping.

Three tree modes:

* ``columns``: one column per level (Site, Asset, RSW...). A row's deepest filled level is its leaf.
* ``path``: one column holding the whole path (``KAR/101/101.1``) and the level of each segment.
* ``parent_row``: one node per row with its level, code and its parent's code (an earlier row or an
  existing node).

Rules from the client spreadsheets (ADR 0003 §5): codes are always text (a number cell ``101.1`` is the
code "101.1"; a date in a code column is converted and flagged); ``#N/A``-style errors become empty with a
warning; a multi-value leaf cell (``101.1 and 101.3 ; 102``) makes one node per value, each getting the
row's fields. Existing nodes are matched by level, code and parent (or by code alone where the level's
codes are unique per level or project), so re-importing updates instead of duplicating.

Every row runs in its own savepoint: a bad row is reported and rolled back, the rest go through. A dry run
does the same work and rolls the whole transaction back, so what it reports is exactly what apply does;
apply commits once at the end.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import DomainError
from . import service
from .constants import CodeUniqueness, NodeStatus
from .models import AssetItem, AssetLevel, AssetNode, ItemIdentifier, ItemType
from .schemas import TreeImportMapping, TreeMode, UpdateMode

ERROR_CELL = re.compile(r"^#(N/?A|REF!|VALUE!|DIV/0!|NAME\?|NULL!|NUM!|SPILL!|CALC!|GETTING_DATA)$", re.IGNORECASE)
MULTI_VALUE = re.compile(r"\s*(?:;|,|&|\+|\band\b)\s*", re.IGNORECASE)
MAX_ACTIONS = 1000

NODE_FIELDS: dict[str, str] = {
    "name": "text",
    "discipline_code": "text",
    "wbs_code": "text",
    "external_id": "text",
    "external_source": "text",
    "planned_start": "date",
    "planned_finish": "date",
    "budget_qty": "decimal",
    "uom": "text",
    "budget_hours": "decimal",
    "earned_qty": "decimal",
}
ITEM_FIELDS: dict[str, str] = {"spec_ref": "text", "discipline": "text", "notes": "text"}
ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "description", "title"),
    "discipline_code": ("discipline", "disciplinecode"),
    "wbs_code": ("wbs", "wbscode"),
    "external_id": ("externalid", "sourceid"),
    "planned_start": ("start", "plannedstart", "startdate"),
    "planned_finish": ("finish", "plannedfinish", "finishdate", "end", "enddate"),
    "budget_qty": ("budgetqty", "qty", "quantity", "budgetquantity"),
    "uom": ("uom", "unit", "units"),
    "budget_hours": ("budgethours", "budgethrs", "hours", "hrs"),
    "earned_qty": ("earnedqty", "earned"),
}


def norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


# --- cells ---------------------------------------------------------------------------------------------


def as_text(value: Any) -> tuple[str | None, str | None]:
    """A cell as text, the way an identifier must be read. Returns ``(text, warning)``."""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return str(value), None
    if isinstance(value, int):
        return str(value), None
    if isinstance(value, float):
        return (str(int(value)) if value.is_integer() else f"{value:.15g}"), None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f"), None
    if isinstance(value, datetime | date):
        day = value.date() if isinstance(value, datetime) else value
        return day.isoformat(), "a date in an identifier column (format the column as text in the source)"
    text = str(value).strip()
    return (text or None), None


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{text}' isn't a date")


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' isn't a number") from exc


def parse(kind: str, value: Any) -> Any:
    if kind == "date":
        return as_date(value)
    if kind == "decimal":
        return as_decimal(value)
    return as_text(value)[0]


def split_values(text: str) -> list[str]:
    return [p for p in (s.strip() for s in MULTI_VALUE.split(text)) if p]


def set_path(target: dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        nxt = target.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            target[k] = nxt
        target = nxt
    target[keys[-1]] = value


def json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        return value.strip() or None
    return value


# --- the mapping ---------------------------------------------------------------------------------------


def guess_mapping(columns: list[str], levels: list[AssetLevel]) -> TreeImportMapping:
    """A first guess from the headers: level labels and keys, node fields by name, a tag column for items."""
    by_norm = {norm(c): c for c in columns}
    level_columns = {}
    for lv in levels:
        for candidate in (lv.key, lv.label, lv.label_plural, f"{lv.label} code", f"{lv.key} code"):
            if norm(candidate) in by_norm:
                level_columns[lv.key] = by_norm[norm(candidate)]
                break
    used = set(level_columns.values())
    node_fields = {}
    for f, aliases in ALIASES.items():
        for a in aliases:
            col = by_norm.get(a)
            if col and col not in used:
                node_fields[f] = col
                used.add(col)
                break
    mode = TreeMode.COLUMNS
    path_column = next((by_norm[k] for k in ("path", "location", "breakdown") if k in by_norm), None)
    if not level_columns and path_column:
        mode = TreeMode.PATH
    return TreeImportMapping(
        tree_mode=mode,
        level_columns=level_columns,
        path_column=path_column if mode == TreeMode.PATH else None,
        path_levels=[lv.key for lv in levels] if mode == TreeMode.PATH else [],
        node_fields=node_fields,
    )


class Columns:
    """Finds a mapped column in this file: exact header, then case/punctuation-insensitive, then a synonym."""

    def __init__(self, columns: list[str], synonyms: dict[str, list[str]]):
        self.exact = set(columns)
        self.by_norm = {norm(c): c for c in columns}
        self.synonyms = synonyms

    def find(self, name: str | None) -> str | None:
        if not name:
            return None
        if name in self.exact:
            return name
        for candidate in [name, *self.synonyms.get(name, [])]:
            hit = self.by_norm.get(norm(candidate))
            if hit:
                return hit
        return None


def missing_columns(mapping: TreeImportMapping, cols: Columns) -> list[str]:
    wanted: list[str | None] = [
        *mapping.level_columns.values(),
        *mapping.node_fields.values(),
        *mapping.custom_fields.values(),
        mapping.path_column,
        mapping.code_column,
        mapping.parent_column,
        mapping.level_column,
    ]
    if mapping.item:
        wanted += [
            mapping.item.tag_column,
            mapping.item.item_type_column,
            *mapping.item.fields.values(),
            *mapping.item.custom_fields.values(),
            *mapping.item.identifiers.values(),
        ]
    return sorted({w for w in wanted if w and cols.find(w) is None})


# --- running -------------------------------------------------------------------------------------------


class RowError(Exception):
    pass


@dataclass
class Report:
    dry_run: bool
    rows: int = 0
    nodes_created: int = 0
    nodes_updated: int = 0
    nodes_unchanged: int = 0
    items_created: int = 0
    items_updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    COUNTERS = ("nodes_created", "nodes_updated", "nodes_unchanged", "items_created", "items_updated")

    def counts(self) -> tuple[tuple[int, ...], int]:
        return tuple(getattr(self, c) for c in self.COUNTERS), len(self.actions)

    def restore(self, saved: tuple[tuple[int, ...], int]) -> None:
        for c, v in zip(self.COUNTERS, saved[0], strict=True):
            setattr(self, c, v)
        del self.actions[saved[1] :]

    def act(self, line: int, action: str, kind: str, label: str, display: str) -> None:
        if len(self.actions) < MAX_ACTIONS:
            self.actions.append({"line": line, "action": action, "kind": kind, "label": label, "display": display})


class Importer:
    def __init__(self, db: AsyncSession, project_id: int, mapping: TreeImportMapping, columns: list[str], dry_run: bool):
        self.db = db
        self.project_id = project_id
        self.m = mapping
        self.cols = Columns(columns, mapping.synonyms)
        self.report = Report(dry_run=dry_run)
        self.levels: dict[str, AssetLevel] = {}
        self.item_types: dict[str, str] = {}
        """Normalised key and name → key."""
        self.by_code: dict[str, int] = {}
        """Codes this file created or touched (parent-row mode resolves parents through it)."""

    # cells

    def cell(self, row: dict[str, Any], column: str | None, line: int) -> Any:
        col = self.cols.find(column)
        if col is None:
            return None
        value = row.get(col)
        if isinstance(value, str):
            value = value.strip()
            if ERROR_CELL.match(value):
                self.report.warnings.append(f"Row {line}: '{col}' holds {value}; read as empty.")
                return None
            if value == "":
                return None
        return value

    def text(self, row: dict[str, Any], column: str | None, line: int) -> str | None:
        text, warning = as_text(self.cell(row, column, line))
        if warning:
            self.report.warnings.append(f"Row {line}: '{self.cols.find(column)}' {warning}.")
        return text

    def level(self, key: str) -> AssetLevel:
        if key not in self.levels:
            raise RowError(f"there's no level '{key}' in this project")
        return self.levels[key]

    def level_named(self, text: str) -> AssetLevel:
        for lv in self.levels.values():
            if norm(text) in {norm(lv.key), norm(lv.label), norm(lv.label_plural)}:
                return lv
        raise RowError(f"'{text}' isn't a level of this project")

    # nodes

    async def find_node(self, level: AssetLevel, code: str, parent_id: int | None) -> AssetNode | None:
        base = select(AssetNode).where(
            AssetNode.project_id == self.project_id,
            AssetNode.level_key == level.key,
            AssetNode.code == code,
            AssetNode.status == NodeStatus.ACTIVE.value,
        )
        node = await self.db.scalar(
            base.where(AssetNode.parent_id == parent_id if parent_id else AssetNode.parent_id.is_(None)).limit(1)
        )
        if node is None and level.code_uniqueness in (CodeUniqueness.PER_LEVEL, CodeUniqueness.PER_PROJECT):
            node = await self.db.scalar(base.limit(1))
        return node

    def node_values(self, row: dict[str, Any], line: int) -> tuple[dict[str, Any], dict[str, Any]]:
        values: dict[str, Any] = {}
        for f, column in self.m.node_fields.items():
            raw = self.cell(row, column, line)
            if raw is None:
                continue
            try:
                values[f] = parse(NODE_FIELDS[f], raw) if NODE_FIELDS[f] != "text" else self.text(row, column, line)
            except ValueError as exc:
                raise RowError(f"{f}: {exc}") from exc
        custom: dict[str, Any] = {}
        for path, column in self.m.custom_fields.items():
            raw = self.cell(row, column, line)
            if raw is not None:
                set_path(custom, path, json_value(raw))
        return values, custom

    async def ensure(
        self,
        level: AssetLevel,
        code: str,
        parent: AssetNode | None,
        line: int,
        values: dict[str, Any] | None = None,
        custom: dict[str, Any] | None = None,
    ) -> AssetNode:
        """Find or create one node; the leaf (``values`` given) is updated as the update mode says."""
        leaf = values is not None
        node = await self.find_node(level, code, parent.id if parent else None)
        if node is None:
            if self.m.update_mode == UpdateMode.UPDATE:
                raise RowError(f"there's no {level.label} '{code}' to update")
            node = await service.create_node(
                self.db,
                self.project_id,
                {
                    "level_key": level.key,
                    "code": code,
                    "parent_id": parent.id if parent else None,
                    **(values or {}),
                    "custom_fields": custom or {},
                },
            )
            self.report.nodes_created += 1
            self.report.act(line, "create", "node", level.label, node.display_path)
        elif leaf and self.m.update_mode != UpdateMode.CREATE:
            changed = False
            for k, v in (values or {}).items():
                if getattr(node, k) != v:
                    setattr(node, k, v)
                    changed = True
            if custom:
                merged = _merge(node.custom_fields or {}, custom)
                if merged != node.custom_fields:
                    node.custom_fields = merged
                    changed = True
            if changed:
                self.report.nodes_updated += 1
                self.report.act(line, "update", "node", level.label, node.display_path)
            else:
                self.report.nodes_unchanged += 1
        elif leaf:
            self.report.nodes_unchanged += 1
        self.by_code[code] = node.id
        return node

    async def parent_by_code(self, code: str) -> AssetNode:
        if code in self.by_code:
            return await service.get_node(self.db, self.by_code[code])
        found = list(
            (
                await self.db.execute(
                    select(AssetNode)
                    .where(
                        AssetNode.project_id == self.project_id,
                        AssetNode.code == code,
                        AssetNode.status == NodeStatus.ACTIVE.value,
                    )
                    .limit(2)
                )
            ).scalars()
        )
        if len(found) != 1:
            raise RowError(f"parent '{code}' " + ("matches several nodes" if found else "isn't in the file or the tree"))
        return found[0]

    async def chain(self, row: dict[str, Any], line: int) -> tuple[list[tuple[AssetLevel, str]], AssetNode | None]:
        """Root-to-leaf ``(level, code)`` pairs for this row, and the existing parent of the first one."""
        if self.m.tree_mode == TreeMode.COLUMNS:
            ordered = sorted(self.m.level_columns.items(), key=lambda kv: (self.level(kv[0]).depth, self.level(kv[0]).id))
            pairs = [(self.level(k), self.text(row, col, line)) for k, col in ordered]
            return [(lv, code) for lv, code in pairs if code], None
        if self.m.tree_mode == TreeMode.PATH:
            path = self.text(row, self.m.path_column, line)
            if not path:
                return [], None
            segments = [s.strip() for s in path.split(self.m.path_separator) if s.strip()]
            if len(segments) > len(self.m.path_levels):
                raise RowError(f"'{path}' has {len(segments)} parts but the mapping names {len(self.m.path_levels)} levels")
            return [(self.level(k), s) for k, s in zip(self.m.path_levels, segments, strict=False)], None
        code = self.text(row, self.m.code_column, line)
        if not code:
            return [], None
        level_text = self.text(row, self.m.level_column, line)
        if not level_text:
            raise RowError("no level given")
        parent_code = self.text(row, self.m.parent_column, line)
        parent = await self.parent_by_code(parent_code) if parent_code else None
        return [(self.level_named(level_text), code)], parent

    async def item(self, row: dict[str, Any], node: AssetNode, line: int) -> None:
        im = self.m.item
        assert im is not None
        tag = self.text(row, im.tag_column, line)
        if not tag:
            return
        type_key = self.text(row, im.item_type_column, line) if im.item_type_column else im.item_type_key
        values: dict[str, Any] = {}
        for f, column in im.fields.items():
            v = self.text(row, column, line)
            if v is not None:
                values[f] = v
        custom: dict[str, Any] = {}
        for path, column in im.custom_fields.items():
            raw = self.cell(row, column, line)
            if raw is not None:
                set_path(custom, path, json_value(raw))
        item = await self.db.scalar(
            select(AssetItem).where(AssetItem.project_id == self.project_id, func.lower(AssetItem.tag) == tag.lower())
        )
        if item is None:
            if self.m.update_mode == UpdateMode.UPDATE:
                raise RowError(f"there's no item '{tag}' to update")
            if not type_key:
                raise RowError(f"item '{tag}' has no item type")
            key = self.item_types.get(norm(type_key))
            if key is None:
                raise RowError(f"unknown item type '{type_key}'")
            item = await service.create_item(
                self.db,
                self.project_id,
                {"node_id": node.id, "item_type_key": key, "tag": tag, **values, "custom_fields": custom},
            )
            self.report.items_created += 1
            self.report.act(line, "create", "item", key, f"{node.display_path} · {tag}")
        elif self.m.update_mode != UpdateMode.CREATE:
            changed = False
            if item.node_id != node.id:
                raise RowError(f"item '{tag}' sits under another node; move it in the tree, not by import")
            for k, v in values.items():
                if getattr(item, k) != v:
                    setattr(item, k, v)
                    changed = True
            merged = _merge(item.custom_fields or {}, custom)
            if merged != item.custom_fields:
                item.custom_fields = merged
                changed = True
            if changed:
                self.report.items_updated += 1
                self.report.act(line, "update", "item", item.item_type_key, f"{node.display_path} · {tag}")
        for kind, column in im.identifiers.items():
            value = self.text(row, column, line)
            if not value:
                continue
            normal = service.normalise_identifier(kind.value, value)
            mine = await self.db.scalar(
                select(ItemIdentifier.id).where(
                    ItemIdentifier.item_id == item.id,
                    ItemIdentifier.kind == kind.value,
                    ItemIdentifier.value == normal,
                    ItemIdentifier.is_active.is_(True),
                )
            )
            if mine is None:
                await service.add_identifier(self.db, item, kind.value, value)

    async def row(self, row: dict[str, Any], line: int) -> None:
        pairs, parent = await self.chain(row, line)
        if not pairs:
            self.report.skipped += 1
            return
        *ancestors, (leaf_level, leaf_text) = pairs
        for level, code in ancestors:
            parent = await self.ensure(level, code, parent, line)
        codes = split_values(leaf_text) if self.m.split_multi_values else [leaf_text]
        if len(codes) > 1:
            self.report.warnings.append(f"Row {line}: '{leaf_text}' split into {len(codes)} {leaf_level.label_plural}.")
        values, custom = self.node_values(row, line)
        leaves = [await self.ensure(leaf_level, code, parent, line, values, custom) for code in codes]
        if self.m.item:
            if len(leaves) > 1 and self.text(row, self.m.item.tag_column, line):
                self.report.warnings.append(f"Row {line}: the item goes on the first of the split nodes only.")
            await self.item(row, leaves[0], line)

    async def run(self, rows: list[dict[str, Any]]) -> Report:
        self.levels = await service.levels_by_key(self.db, self.project_id)
        for t in (await self.db.execute(select(ItemType).where(ItemType.project_id == self.project_id))).scalars():
            self.item_types[norm(t.key)] = self.item_types[norm(t.name)] = t.key
        missing = missing_columns(self.m, self.cols)
        if missing:
            self.report.errors.append("Columns not in the file: " + ", ".join(missing))
            return self.report
        self.report.rows = len(rows)
        for i, row in enumerate(rows):
            line = i + 2
            known, counts = dict(self.by_code), self.report.counts()
            savepoint = await self.db.begin_nested()
            try:
                await self.row(row, line)
                await savepoint.commit()
            except (RowError, DomainError, ValueError) as exc:
                await savepoint.rollback()
                self.by_code = known
                self.report.restore(counts)
                self.report.skipped += 1
                self.report.errors.append(f"Row {line}: {_message(exc)}")
        return self.report


def _message(exc: Exception) -> str:
    detail = getattr(exc, "public_detail", None)
    if not detail:
        return str(exc)
    return detail if not str(exc) or str(exc) in detail else f"{detail} ({exc})"


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


async def run_import(
    db: AsyncSession, project_id: int, mapping: TreeImportMapping, columns: list[str], rows: list[dict[str, Any]], dry_run: bool
) -> Report:
    report = await Importer(db, project_id, mapping, columns, dry_run).run(rows)
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return report
