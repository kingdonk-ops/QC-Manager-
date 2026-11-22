"""The breakdown's rules. Everything that changes the tree goes through here."""

import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ..common.exceptions import ResourceExistsError, ResourceNotFoundError, ValidationError
from .constants import CodeUniqueness, NodeStatus, Role
from .models import AssetItem, AssetLevel, AssetNode, ItemIdentifier, ItemType


class NodeNotFound(ResourceNotFoundError):
    public_detail = "Asset node not found."


class LevelNotFound(ResourceNotFoundError):
    public_detail = "Breakdown level not found."


class ItemNotFound(ResourceNotFoundError):
    public_detail = "Item not found."


class TreeRuleError(ValidationError):
    public_detail = "That change breaks the breakdown's rules."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class NoWorkAnchor(TreeRuleError):
    def __init__(self) -> None:
        super().__init__("There is no work anchor (e.g. RSW) on this node's path. Pick or create one first.")


class DuplicateCode(ResourceExistsError):
    public_detail = "Another node already uses that code in the same scope."


# --- reading -----------------------------------------------------------------------------------------


async def get_level(db: AsyncSession, project_id: int, key: str) -> AssetLevel:
    level = await db.scalar(select(AssetLevel).where(AssetLevel.project_id == project_id, AssetLevel.key == key))
    if level is None:
        raise LevelNotFound(key)
    return level


async def get_node(db: AsyncSession, node_id: int, project_id: int | None = None) -> AssetNode:
    node = await db.get(AssetNode, node_id)
    if node is None or (project_id is not None and node.project_id != project_id):
        raise NodeNotFound(str(node_id))
    return node


async def get_item(db: AsyncSession, item_id: int, project_id: int | None = None) -> AssetItem:
    item = await db.get(AssetItem, item_id)
    if item is None or (project_id is not None and item.project_id != project_id):
        raise ItemNotFound(str(item_id))
    return item


def path_ids(node: AssetNode) -> list[int]:
    return [int(p) for p in node.path.strip("/").split("/") if p]


async def node_path(db: AsyncSession, node_id: int) -> list[AssetNode]:
    """Root-to-node, inclusive."""
    node = await get_node(db, node_id)
    ids = path_ids(node)
    rows = {n.id: n for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(ids)))).scalars()}
    return [rows[i] for i in ids if i in rows]


async def levels_by_key(db: AsyncSession, project_id: int) -> dict[str, AssetLevel]:
    rows = (await db.execute(select(AssetLevel).where(AssetLevel.project_id == project_id))).scalars()
    return {lv.key: lv for lv in rows}


async def has_role(db: AsyncSession, node: AssetNode, role: Role) -> bool:
    level = await db.get(AssetLevel, node.level_id)
    return bool(level and role.value in level.roles)


async def work_anchor_for(db: AsyncSession, node_id: int) -> AssetNode:
    """The work-anchor node on the node's root-to-leaf path (itself, an ancestor or the one descendant chain).

    Raises ``NoWorkAnchor`` (422) when the path has none: booking work needs one.
    """
    path = await node_path(db, node_id)
    levels = {
        lv.id: lv
        for lv in (await db.execute(select(AssetLevel).where(AssetLevel.id.in_({n.level_id for n in path})))).scalars()
    }
    for node in path:
        if Role.WORK_ANCHOR.value in levels[node.level_id].roles:
            return node
    raise NoWorkAnchor()


async def subtree_ids(db: AsyncSession, node_id: int, *, with_lineage: bool = True) -> list[int]:
    """The node, its descendants, and (with lineage) the nodes it was split or merged from."""
    node = await get_node(db, node_id)
    ids = set((await db.execute(select(AssetNode.id).where(AssetNode.path.like(f"{node.path}%")))).scalars())
    if with_lineage:
        frontier = set(ids)
        while frontier:
            sources = set()
            for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(frontier)))).scalars():
                sources |= {int(x) for x in n.derived_from}
            sources -= ids
            for s in list(sources):
                src = await db.get(AssetNode, s)
                if src:
                    ids |= set((await db.execute(select(AssetNode.id).where(AssetNode.path.like(f"{src.path}%")))).scalars())
            frontier = sources
    return sorted(ids)


# --- rules -------------------------------------------------------------------------------------------


def _scope(level: AssetLevel, parent: AssetNode | None) -> str:
    if level.code_uniqueness == CodeUniqueness.PER_PROJECT:
        return "project"
    if level.code_uniqueness == CodeUniqueness.PER_LEVEL:
        return f"level:{level.key}"
    return f"parent:{parent.id if parent else 0}:{level.key}"


def _check_code(level: AssetLevel, code: str) -> None:
    if not code.strip():
        raise TreeRuleError("A code is required.")
    if level.code_pattern and not re.fullmatch(level.code_pattern, code):
        raise TreeRuleError(f"'{code}' doesn't match the {level.label} code pattern {level.code_pattern}.")


def _check_parent(level: AssetLevel, parent: AssetNode | None) -> None:
    allowed = level.allowed_parent_keys or []
    if parent is None and allowed and "" not in allowed:
        raise TreeRuleError(f"A {level.label} must sit under one of: {', '.join(allowed)}.")
    if parent is not None and parent.level_key not in allowed:
        raise TreeRuleError(f"A {level.label} can't sit under a {parent.level_key}.")
    if parent is not None and parent.status == NodeStatus.RETIRED:
        raise TreeRuleError("Nothing new can be added under a retired node.")


async def _check_work_anchor_nesting(
    db: AsyncSession, level: AssetLevel, parent: AssetNode | None, subtree_root: AssetNode | None = None
) -> None:
    """At most one work anchor on any root-to-leaf path."""
    ancestors = await node_path(db, parent.id) if parent else []
    ancestor_levels = (
        {
            lv.id: lv
            for lv in (await db.execute(select(AssetLevel).where(AssetLevel.id.in_({n.level_id for n in ancestors})))).scalars()
        }
        if ancestors
        else {}
    )
    ancestor_anchor = any(Role.WORK_ANCHOR.value in ancestor_levels[n.level_id].roles for n in ancestors)
    moving_has_anchor = Role.WORK_ANCHOR.value in level.roles
    if subtree_root is not None:
        sub = (await db.execute(select(AssetNode.level_id).where(AssetNode.path.like(f"{subtree_root.path}%")))).scalars().all()
        sub_levels = (await db.execute(select(AssetLevel.roles).where(AssetLevel.id.in_(set(sub))))).scalars().all()
        moving_has_anchor = any(Role.WORK_ANCHOR.value in r for r in sub_levels)
    if ancestor_anchor and moving_has_anchor:
        raise TreeRuleError("Work anchors can't be nested: this path already has one above.")


def _display_code(level: AssetLevel, path_codes: dict[str, str]) -> str | None:
    if not level.display_code_template:
        return None
    try:
        return level.display_code_template.format_map(
            {k: path_codes.get(k, "") for k in re.findall(r"{(\w+)}", level.display_code_template)}
        )
    except (KeyError, ValueError):
        return None


# --- changing ----------------------------------------------------------------------------------------


async def create_node(db: AsyncSession, project_id: int, values: dict[str, Any]) -> AssetNode:
    level = await get_level(db, project_id, values.pop("level_key"))
    parent = await get_node(db, values["parent_id"], project_id) if values.get("parent_id") else None
    _check_parent(level, parent)
    _check_code(level, values["code"])
    await _check_work_anchor_nesting(db, level, parent)
    scope = _scope(level, parent)
    if await db.scalar(
        select(AssetNode.id).where(
            AssetNode.project_id == project_id, AssetNode.code_scope == scope, AssetNode.code == values["code"]
        )
    ):
        raise DuplicateCode(values["code"])
    node = AssetNode(project_id=project_id, level_id=level.id, level_key=level.key, code_scope=scope, **values)
    db.add(node)
    await db.flush()
    ancestors = await node_path(db, parent.id) if parent else []
    node.path = f"{parent.path if parent else '/'}{node.id}/"
    node.display_path = " / ".join([n.code for n in ancestors] + [node.code])
    node.display_code = _display_code(level, {n.level_key: n.code for n in [*ancestors, node]})
    await db.flush()
    return node


async def move_node(db: AsyncSession, node: AssetNode, new_parent_id: int | None) -> None:
    level = await db.get(AssetLevel, node.level_id)
    assert level is not None
    parent = await get_node(db, new_parent_id, node.project_id) if new_parent_id else None
    if parent is not None and parent.path.startswith(node.path):
        raise TreeRuleError("A node can't move under itself.")
    _check_parent(level, parent)
    await _check_work_anchor_nesting(db, level, parent, subtree_root=node)
    old_path, old_display = node.path, node.display_path
    new_path = f"{parent.path if parent else '/'}{node.id}/"
    new_display = f"{parent.display_path} / {node.code}" if parent else node.code
    scope = _scope(level, parent)
    if await db.scalar(
        select(AssetNode.id).where(
            AssetNode.project_id == node.project_id,
            AssetNode.code_scope == scope,
            AssetNode.code == node.code,
            AssetNode.id != node.id,
        )
    ):
        raise DuplicateCode(node.code)
    await db.execute(
        update(AssetNode)
        .where(AssetNode.project_id == node.project_id, AssetNode.path.like(f"{old_path}%"))
        .values(
            path=func.concat(new_path, func.substr(AssetNode.path, len(old_path) + 1)),
            display_path=func.concat(new_display, func.substr(AssetNode.display_path, len(old_display) + 1)),
        )
        .execution_options(synchronize_session=False)
    )
    node.parent_id = parent.id if parent else None
    node.code_scope = scope
    await db.flush()
    await db.refresh(node)
    await publish("asset_tree.node.moved", {"node_id": node.id, "from": old_display, "to": node.display_path})


async def retire(db: AsyncSession, node: AssetNode, superseded_by: Iterable[int] = ()) -> None:
    node.status = NodeStatus.RETIRED.value
    node.superseded_by = sorted(set(node.superseded_by) | set(superseded_by))
    await db.flush()


async def split(db: AsyncSession, source: AssetNode, parts: list[dict[str, Any]]) -> list[AssetNode]:
    """Retire the source; each part becomes a sibling derived from it."""
    if source.status == NodeStatus.RETIRED:
        raise TreeRuleError("That node is already retired.")
    created = []
    for part in parts:
        node = await create_node(db, source.project_id, {"level_key": source.level_key, "parent_id": source.parent_id, **part})
        node.derived_from = [source.id]
        created.append(node)
    await retire(db, source, [n.id for n in created])
    return created


async def merge(db: AsyncSession, sources: list[AssetNode], target: AssetNode) -> None:
    for s in sources:
        if s.id == target.id:
            raise TreeRuleError("A node can't merge into itself.")
        await retire(db, s, [target.id])
    target.derived_from = sorted(set(target.derived_from) | {s.id for s in sources})
    await db.flush()


async def create_item(db: AsyncSession, project_id: int, values: dict[str, Any]) -> AssetItem:
    node = await get_node(db, values["node_id"], project_id)
    if node.status == NodeStatus.RETIRED:
        raise TreeRuleError("Items can't be added to a retired node.")
    item_type = await db.scalar(
        select(ItemType).where(ItemType.project_id == project_id, ItemType.key == values["item_type_key"])
    )
    if item_type is None:
        raise TreeRuleError(f"Unknown item type '{values['item_type_key']}'.")
    anchor_id = values.get("work_anchor_id")
    if anchor_id:
        anchor = await get_node(db, anchor_id, project_id)
        if not await has_role(db, anchor, Role.WORK_ANCHOR):
            raise TreeRuleError("The work anchor must be a node whose level is a work anchor.")
        if not (node.path.startswith(anchor.path) or anchor.path.startswith(node.path)):
            raise TreeRuleError("The work anchor must be on the item's root-to-leaf path.")
    else:
        try:
            values["work_anchor_id"] = (await work_anchor_for(db, node.id)).id
        except NoWorkAnchor:
            values["work_anchor_id"] = None
    item = AssetItem(project_id=project_id, type_revision=item_type.revision, inspectable=item_type.inspectable, **values)
    db.add(item)
    await db.flush()
    return item


def normalise_identifier(kind: str, value: str) -> str:
    value = value.strip()
    return re.sub(r"[^0-9A-Fa-f]", "", value).upper() if kind == "nfc" else value


async def add_identifier(db: AsyncSession, item: AssetItem, kind: str, value: str) -> ItemIdentifier:
    value = normalise_identifier(kind, value)
    clash = await db.scalar(
        select(ItemIdentifier).where(
            ItemIdentifier.project_id == item.project_id,
            ItemIdentifier.kind == kind,
            ItemIdentifier.value == value,
            ItemIdentifier.is_active.is_(True),
        )
    )
    if clash is not None:
        raise ResourceExistsError(f"{kind} {value} is already on item {clash.item_id}")
    ident = ItemIdentifier(project_id=item.project_id, item_id=item.id, kind=kind, value=value)
    db.add(ident)
    await db.flush()
    return ident


async def lookup(db: AsyncSession, project_id: int, value: str, kind: str | None) -> AssetItem:
    candidates = (
        [(kind, normalise_identifier(kind, value))]
        if kind
        else [(k, normalise_identifier(k, value)) for k in ("barcode", "qr", "nfc")]
    )
    for k, v in candidates:
        ident = await db.scalar(
            select(ItemIdentifier).where(
                ItemIdentifier.project_id == project_id,
                ItemIdentifier.kind == k,
                ItemIdentifier.value == v,
                ItemIdentifier.is_active.is_(True),
            )
        )
        if ident:
            return await get_item(db, ident.item_id, project_id)
    by_tag = await db.scalar(
        select(AssetItem).where(AssetItem.project_id == project_id, func.lower(AssetItem.tag) == value.strip().lower())
    )
    if by_tag:
        return by_tag
    raise ItemNotFound(value)
