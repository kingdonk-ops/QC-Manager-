"""Where a record belongs (KERP ADR 0003 §6 and its 2026-11-21 amendment).

A ``qa_itp`` record *belongs to an asset*: it anchors to a node whose level has the ``inspection_anchor``
role, or to an asset Item. A record of any other area belongs to the *project*: no anchor, an optional
informational location node and optional links to nodes, Items or equipment. Location and links never roll
up, never feed progress and never satisfy a completion gate.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import NotFoundException, UnprocessableEntityException
from ..asset_tree import service as tree
from ..asset_tree.constants import NodeStatus, Role
from ..asset_tree.models import AssetItem, AssetNode
from ..assets.models import AssetComponent
from .constants import Area, LinkKind
from .models import InspectionLink


async def check_anchor(db: AsyncSession, project_id: int, node_id: int | None, item_id: int | None) -> None:
    """Exactly one of node / Item; the node's level must have the ``inspection_anchor`` role."""
    if (node_id is None) == (item_id is None):
        raise UnprocessableEntityException("A QA/ITP record anchors to exactly one inspection-anchor node or one asset Item.")
    if node_id is not None:
        node = await tree.get_node(db, node_id, project_id)
        if node.status == NodeStatus.RETIRED:
            raise UnprocessableEntityException("That node is retired; anchor to the node that superseded it.")
        if not await tree.has_role(db, node, Role.INSPECTION_ANCHOR):
            raise UnprocessableEntityException(
                f"{node.display_path or node.code} is not an inspection anchor: pick a node whose level can carry "
                "inspections, or an Item."
            )
    else:
        assert item_id is not None
        item = await tree.get_item(db, item_id, project_id)
        if item.status == "retired":
            raise UnprocessableEntityException("That Item is retired.")


async def check_placement(
    db: AsyncSession,
    project_id: int,
    area: str,
    *,
    node_id: int | None,
    item_id: int | None,
    location_node_id: int | None,
    links: list[dict[str, Any]],
) -> None:
    if area == Area.QA_ITP:
        await check_anchor(db, project_id, node_id, item_id)
        if location_node_id is not None or links:
            raise UnprocessableEntityException(
                "A QA/ITP record is located by its anchor; location and links are for project-level records."
            )
        return
    if node_id is not None or item_id is not None:
        raise UnprocessableEntityException(
            "Only QA/ITP records anchor to the asset tree; give this record a location or links instead."
        )
    if location_node_id is not None:
        await tree.get_node(db, location_node_id, project_id)
    equipment = [link for link in links if link["kind"] == LinkKind.EQUIPMENT]
    if len(equipment) > 1:
        raise UnprocessableEntityException("A record links to at most one piece of equipment.")
    for link in links:
        await check_link_target(db, project_id, str(link["kind"]), int(link["id"]))


async def check_link_target(db: AsyncSession, project_id: int, kind: str, target_id: int) -> None:
    if kind == LinkKind.NODE:
        await tree.get_node(db, target_id, project_id)
    elif kind == LinkKind.ITEM:
        await tree.get_item(db, target_id, project_id)
    elif kind == LinkKind.EQUIPMENT:
        component = await db.get(AssetComponent, target_id)
        if component is None or component.project_id != project_id:
            raise NotFoundException("Equipment not found.")


async def add_links(db: AsyncSession, inspection_id: int, links: list[dict[str, Any]]) -> None:
    seen = set()
    for link in links:
        key = (str(link["kind"]), int(link["id"]))
        if key not in seen:
            seen.add(key)
            db.add(InspectionLink(inspection_id=inspection_id, target_kind=key[0], target_id=key[1]))


async def links_of(db: AsyncSession, inspection_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not inspection_ids:
        return {}
    rows = list(
        (
            await db.execute(
                select(InspectionLink).where(InspectionLink.inspection_id.in_(inspection_ids)).order_by(InspectionLink.id)
            )
        ).scalars()
    )
    labels = await _labels(db, [(r.target_kind, r.target_id) for r in rows])
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r.inspection_id, []).append(
            {"kind": r.target_kind, "id": r.target_id, "label": labels.get((r.target_kind, r.target_id))}
        )
    return out


async def anchor_labels(
    db: AsyncSession, pairs: list[tuple[int | None, int | None]]
) -> dict[tuple[int | None, int | None], str]:
    """``(node_id, item_id)`` → the node's display path, or the Item's tag with its node's path."""
    wanted: list[tuple[str, int]] = []
    for node_id, item_id in pairs:
        if node_id:
            wanted.append((LinkKind.NODE.value, node_id))
        if item_id:
            wanted.append((LinkKind.ITEM.value, item_id))
    labels = await _labels(db, wanted)
    out: dict[tuple[int | None, int | None], str] = {}
    for node_id, item_id in pairs:
        label = labels.get((LinkKind.NODE.value, node_id)) if node_id else None
        if item_id:
            label = labels.get((LinkKind.ITEM.value, item_id))
        if label:
            out[(node_id, item_id)] = label
    return out


async def _labels(db: AsyncSession, wanted: list[tuple[str, int]]) -> dict[tuple[str, int], str]:
    node_ids = {i for k, i in wanted if k == LinkKind.NODE}
    item_ids = {i for k, i in wanted if k == LinkKind.ITEM}
    equipment_ids = {i for k, i in wanted if k == LinkKind.EQUIPMENT}
    out: dict[tuple[str, int], str] = {}
    items: list[AssetItem] = []
    if item_ids:
        items = list((await db.execute(select(AssetItem).where(AssetItem.id.in_(item_ids)))).scalars())
        node_ids |= {i.node_id for i in items}
    nodes: dict[int, AssetNode] = {}
    if node_ids:
        nodes = {n.id: n for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_(node_ids)))).scalars()}
        for n in nodes.values():
            out[(LinkKind.NODE.value, n.id)] = n.display_path or n.code
    for item in items:
        where = nodes.get(item.node_id)
        out[(LinkKind.ITEM.value, item.id)] = f"{item.tag} ({where.display_path or where.code})" if where else item.tag
    if equipment_ids:
        for c in (await db.execute(select(AssetComponent).where(AssetComponent.id.in_(equipment_ids)))).scalars():
            out[(LinkKind.EQUIPMENT.value, c.id)] = c.tag_number or c.name
    return out


async def anchored_in(db: AsyncSession, node_id: int) -> tuple[list[int], list[int]]:
    """Node ids of the subtree (with lineage) and the ids of the Items under them, for a register filter."""
    nodes = await tree.subtree_ids(db, node_id, with_lineage=True)
    items = list((await db.execute(select(AssetItem.id).where(AssetItem.node_id.in_(nodes)))).scalars())
    return nodes, items
