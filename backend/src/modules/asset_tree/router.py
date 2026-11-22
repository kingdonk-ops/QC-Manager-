"""Mounted at /api/v1/asset-tree."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import delete, func, or_, select

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import IdentifierKind, NodeStatus
from .models import AssetCollection, AssetCollectionMember, AssetItem, AssetLevel, AssetNode, ItemIdentifier, ItemType
from .packs import PACKS, apply_pack
from .permissions import AssetTreePermissionName as P
from .schemas import (
    CollectionIn,
    CollectionRead,
    IdentifierIn,
    IdentifierRead,
    ItemIn,
    ItemRead,
    ItemTypeIn,
    ItemTypeRead,
    ItemUpdate,
    LevelIn,
    LevelRead,
    MembersIn,
    MergeIn,
    MoveIn,
    NodeIn,
    NodeRead,
    NodeUpdate,
    RetireIn,
    SplitIn,
)

router = APIRouter(tags=["Asset hierarchy"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _node_reads(db: Any, nodes: list[AssetNode]) -> list[dict[str, Any]]:
    ids = [n.id for n in nodes]
    children = (
        dict(
            (
                await db.execute(
                    select(AssetNode.parent_id, func.count()).where(AssetNode.parent_id.in_(ids)).group_by(AssetNode.parent_id)
                )
            )
            .tuples()
            .all()
        )
        if ids
        else {}
    )
    items = (
        dict(
            (
                await db.execute(
                    select(AssetItem.node_id, func.count()).where(AssetItem.node_id.in_(ids)).group_by(AssetItem.node_id)
                )
            )
            .tuples()
            .all()
        )
        if ids
        else {}
    )
    return [
        NodeRead.model_validate(n)
        .model_copy(update={"child_count": children.get(n.id, 0), "item_count": items.get(n.id, 0)})
        .model_dump(mode="json")
        for n in nodes
    ]


async def _item_reads(db: Any, items: list[AssetItem]) -> list[dict[str, Any]]:
    ids = [i.id for i in items]
    idents: dict[int, list[IdentifierRead]] = {}
    for ident in (await db.execute(select(ItemIdentifier).where(ItemIdentifier.item_id.in_(ids)))).scalars() if ids else []:
        idents.setdefault(ident.item_id, []).append(IdentifierRead.model_validate(ident))
    nodes = (
        {
            n.id: n.display_path
            for n in (await db.execute(select(AssetNode).where(AssetNode.id.in_({i.node_id for i in items})))).scalars()
        }
        if items
        else {}
    )
    return [
        ItemRead.model_validate(i)
        .model_copy(update={"identifiers": idents.get(i.id, []), "node_display_path": nodes.get(i.node_id)})
        .model_dump(mode="json")
        for i in items
    ]


# --- packs and levels ----------------------------------------------------------------------------------


@router.get("/packs", summary="Starting Packs")
async def packs(_: CurrentUserDep) -> list[dict[str, Any]]:
    return [{"key": k, "title": v["title"], "levels": [lv["key"] for lv in v["levels"]]} for k, v in PACKS.items()]


@router.post("/packs/{key}/apply", summary="Apply a Starting Pack to a Project (idempotent)", dependencies=perm(P.CONFIGURE))
async def apply(
    key: Annotated[str, Path(max_length=40)],
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> dict[str, int]:
    await readable_project(db, project_id, user["id"], held)
    if key not in PACKS:
        raise UnprocessableEntityException(f"No pack named {key}")
    return await apply_pack(db, project_id, key)


@router.get("/levels", response_model=list[LevelRead], summary="The Project's Breakdown Levels", dependencies=perm(P.READ))
async def levels(project_id: ProjectQ, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return (
        (
            await db.execute(
                select(AssetLevel).where(AssetLevel.project_id == project_id).order_by(AssetLevel.depth, AssetLevel.id)
            )
        )
        .scalars()
        .all()
    )


@router.post("/levels", response_model=LevelRead, status_code=201, summary="Add a Level", dependencies=perm(P.CONFIGURE))
async def add_level(
    values: LevelIn, project_id: ProjectQ, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    level = AssetLevel(project_id=project_id, **values.model_dump(mode="json"))
    db.add(level)
    await db.commit()
    return level


@router.patch(
    "/levels/{level_id}",
    response_model=LevelRead,
    summary="Change a Level",
    description="The key never changes; labels, patterns, parents and roles can. Roles are re-checked against existing nodes.",
    dependencies=perm(P.CONFIGURE),
)
async def update_level(
    level_id: Id, values: LevelIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    level = await db.get(AssetLevel, level_id)
    if level is None:
        raise service.LevelNotFound(str(level_id))
    await readable_project(db, level.project_id, user["id"], held)
    if values.key != level.key and await db.scalar(select(AssetNode.id).where(AssetNode.level_id == level.id).limit(1)):
        raise UnprocessableEntityException("A level's key can't change once nodes use it.")
    for key, value in values.model_dump(mode="json").items():
        setattr(level, key, value)
    await db.commit()
    return level


# --- nodes ---------------------------------------------------------------------------------------------


@router.get(
    "/nodes/",
    response_model=PaginatedListResponse[NodeRead],
    summary="List Nodes",
    description="Children of `parent_id` (roots when omitted), or search all levels with `search`/`level_key`.",
    dependencies=perm(P.READ),
)
async def list_nodes(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    parent_id: Annotated[int | None, Query(ge=1)] = None,
    level_key: Annotated[str | None, Query(max_length=64)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    include_retired: bool = False,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetNode.project_id == project_id]
    if search or level_key:
        if search:
            like = f"%{search.lower()}%"
            where.append(
                or_(
                    func.lower(AssetNode.code).like(like),
                    func.lower(func.coalesce(AssetNode.name, "")).like(like),
                    func.lower(AssetNode.display_path).like(like),
                )
            )
        if level_key:
            where.append(AssetNode.level_key == level_key)
    else:
        where.append(AssetNode.parent_id == parent_id if parent_id else AssetNode.parent_id.is_(None))
    if not include_retired:
        where.append(AssetNode.status == NodeStatus.ACTIVE.value)
    total = await db.scalar(select(func.count()).select_from(AssetNode).where(*where))
    rows = (
        await db.execute(
            select(AssetNode)
            .where(*where)
            .order_by(AssetNode.code)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return paginated_response(
        crud_data={"data": await _node_reads(db, list(rows)), "total_count": total or 0},
        page=page,
        items_per_page=items_per_page,
    )


@router.post("/nodes/", response_model=NodeRead, status_code=201, summary="Create a Node", dependencies=perm(P.CREATE))
async def create_node(values: NodeIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    data = values.model_dump(exclude={"project_id"})
    node = await service.create_node(db, values.project_id, data)
    await db.commit()
    return (await _node_reads(db, [node]))[0]


@router.get("/nodes/{node_id}", response_model=NodeRead, summary="Get a Node", dependencies=perm(P.READ))
async def get_node(node_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    return (await _node_reads(db, [node]))[0]


@router.get(
    "/nodes/{node_id}/path", response_model=list[NodeRead], summary="Root-to-Node Breadcrumb", dependencies=perm(P.READ)
)
async def path(node_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    return await _node_reads(db, await service.node_path(db, node_id))


@router.get(
    "/nodes/{node_id}/work-anchor",
    response_model=NodeRead,
    summary="The Work Anchor on the Node's Path",
    dependencies=perm(P.READ),
)
async def work_anchor(node_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    return (await _node_reads(db, [await service.work_anchor_for(db, node_id)]))[0]


@router.patch("/nodes/{node_id}", response_model=NodeRead, summary="Update a Node", dependencies=perm(P.UPDATE))
async def update_node(
    node_id: Id, values: NodeUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    await db.commit()
    return (await _node_reads(db, [node]))[0]


@router.post(
    "/nodes/{node_id}/move", response_model=NodeRead, summary="Move a Node and Its Subtree", dependencies=perm(P.UPDATE)
)
async def move(node_id: Id, values: MoveIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    old_parent, old_path = node.parent_id, node.display_path
    await service.move_node(db, node, values.parent_id)
    await record_audit(
        db,
        "asset_tree.node.moved",
        "asset_node",
        node.id,
        actor_id=user["id"],
        project_id=node.project_id,
        summary=f"Moved {node.code}",
        before={"parent_id": old_parent, "display_path": old_path},
        after={"parent_id": node.parent_id, "display_path": node.display_path},
    )
    await db.commit()
    return (await _node_reads(db, [node]))[0]


@router.post(
    "/nodes/{node_id}/split",
    response_model=list[NodeRead],
    summary="Split a Node (the source is retired)",
    dependencies=perm(P.UPDATE),
)
async def split(node_id: Id, values: SplitIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    parts = await service.split(db, node, [p.model_dump() for p in values.parts])
    await record_audit(
        db,
        "asset_tree.node.split",
        "asset_node",
        node.id,
        actor_id=user["id"],
        project_id=node.project_id,
        summary=f"Split {node.code} into {', '.join(p.code for p in parts)}",
        after={"status": node.status, "superseded_by": [p.id for p in parts]},
    )
    await db.commit()
    return await _node_reads(db, parts)


@router.post(
    "/nodes/{node_id}/merge",
    response_model=NodeRead,
    summary="Merge Nodes into This One (sources are retired)",
    dependencies=perm(P.UPDATE),
)
async def merge(node_id: Id, values: MergeIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    target = await service.get_node(db, node_id)
    await readable_project(db, target.project_id, user["id"], held)
    sources = [await service.get_node(db, i, target.project_id) for i in values.source_ids]
    await service.merge(db, sources, target)
    await record_audit(
        db,
        "asset_tree.node.merged",
        "asset_node",
        target.id,
        actor_id=user["id"],
        project_id=target.project_id,
        summary=f"Merged {', '.join(s.code for s in sources)} into {target.code}",
        after={"merged_ids": [s.id for s in sources]},
    )
    await db.commit()
    return (await _node_reads(db, [target]))[0]


@router.post("/nodes/{node_id}/retire", response_model=NodeRead, summary="Retire a Node", dependencies=perm(P.UPDATE))
async def retire(node_id: Id, values: RetireIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    old_status = node.status
    await service.retire(db, node, values.superseded_by)
    await record_audit(
        db,
        "asset_tree.node.retired",
        "asset_node",
        node.id,
        actor_id=user["id"],
        project_id=node.project_id,
        summary=f"Retired {node.code}",
        before={"status": old_status},
        after={"status": node.status, "superseded_by": list(node.superseded_by)},
    )
    await db.commit()
    return (await _node_reads(db, [node]))[0]


@router.delete(
    "/nodes/{node_id}",
    summary="Delete an Empty Node",
    description="Nodes with children or items are retired instead.",
    dependencies=perm(P.DELETE),
)
async def delete_node(node_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    node = await service.get_node(db, node_id)
    await readable_project(db, node.project_id, user["id"], held)
    if await db.scalar(select(AssetNode.id).where(AssetNode.parent_id == node.id).limit(1)) or await db.scalar(
        select(AssetItem.id).where(AssetItem.node_id == node.id).limit(1)
    ):
        raise UnprocessableEntityException("It has children or items: retire it instead.")
    await db.delete(node)
    await db.commit()
    return {"message": "Node deleted"}


# --- item types and items ------------------------------------------------------------------------------


@router.get("/item-types", response_model=list[ItemTypeRead], summary="Item Types", dependencies=perm(P.READ))
async def item_types(project_id: ProjectQ, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return (await db.execute(select(ItemType).where(ItemType.project_id == project_id).order_by(ItemType.name))).scalars().all()


@router.put(
    "/item-types/{key}",
    response_model=ItemTypeRead,
    summary="Create or Revise an Item Type",
    description="Changing the schema makes a new revision; existing items keep the revision they were captured on.",
    dependencies=perm(P.CONFIGURE),
)
async def put_item_type(
    key: Annotated[str, Path(max_length=64)],
    values: ItemTypeIn,
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    existing = await db.scalar(select(ItemType).where(ItemType.project_id == project_id, ItemType.key == key))
    if existing is None:
        existing = ItemType(project_id=project_id, **{**values.model_dump(), "key": key})
        db.add(existing)
    else:
        if values.field_schema != existing.field_schema:
            existing.revision += 1
        existing.name, existing.field_schema, existing.inspectable = values.name, values.field_schema, values.inspectable
    await db.commit()
    return existing


@router.get(
    "/items/",
    response_model=PaginatedListResponse[ItemRead],
    summary="List Items",
    description="Items under `node_id` (with descendants), or search by tag.",
    dependencies=perm(P.READ),
)
async def list_items(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    node_id: Annotated[int | None, Query(ge=1)] = None,
    item_type_key: Annotated[str | None, Query(max_length=64)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetItem.project_id == project_id]
    if node_id:
        where.append(AssetItem.node_id.in_(await service.subtree_ids(db, node_id)))
    if item_type_key:
        where.append(AssetItem.item_type_key == item_type_key)
    if search:
        where.append(func.lower(AssetItem.tag).like(f"%{search.lower()}%"))
    total = await db.scalar(select(func.count()).select_from(AssetItem).where(*where))
    rows = (
        await db.execute(
            select(AssetItem)
            .where(*where)
            .order_by(AssetItem.tag)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return paginated_response(
        crud_data={"data": await _item_reads(db, list(rows)), "total_count": total or 0},
        page=page,
        items_per_page=items_per_page,
    )


@router.get(
    "/items/lookup",
    response_model=ItemRead,
    summary="Scan to Locate",
    description="By barcode, QR or NFC value, falling back to the tag. 404 when nothing in this project matches.",
    dependencies=perm(P.READ),
)
async def lookup(
    project_id: ProjectQ,
    value: Annotated[str, Query(min_length=1, max_length=200)],
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    kind: IdentifierKind | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    item = await service.lookup(db, project_id, value, kind.value if kind else None)
    return (await _item_reads(db, [item]))[0]


@router.post("/items/", response_model=ItemRead, status_code=201, summary="Create an Item", dependencies=perm(P.CREATE))
async def create_item(values: ItemIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    item = await service.create_item(db, values.project_id, values.model_dump(exclude={"project_id"}))
    await db.commit()
    return (await _item_reads(db, [item]))[0]


@router.get("/items/{item_id}", response_model=ItemRead, summary="Get an Item", dependencies=perm(P.READ))
async def get_item(item_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    return (await _item_reads(db, [item]))[0]


@router.patch("/items/{item_id}", response_model=ItemRead, summary="Update an Item", dependencies=perm(P.UPDATE))
async def update_item(
    item_id: Id, values: ItemUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    await db.commit()
    return (await _item_reads(db, [item]))[0]


@router.post(
    "/items/{item_id}/identifiers",
    response_model=ItemRead,
    status_code=201,
    summary="Add a Barcode, QR or NFC Tag",
    dependencies=perm(P.UPDATE),
)
async def add_identifier(
    item_id: Id, values: IdentifierIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    await service.add_identifier(db, item, values.kind.value, values.value)
    await db.commit()
    return (await _item_reads(db, [item]))[0]


@router.delete(
    "/items/{item_id}/identifiers/{identifier_id}", summary="Deactivate a Tag (kept for history)", dependencies=perm(P.UPDATE)
)
async def deactivate_identifier(
    item_id: Id, identifier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    item = await service.get_item(db, item_id)
    await readable_project(db, item.project_id, user["id"], held)
    ident = await db.get(ItemIdentifier, identifier_id)
    if ident is None or ident.item_id != item.id:
        raise service.ItemNotFound(str(identifier_id))
    ident.is_active = False
    await db.commit()
    return {"message": "Tag deactivated"}


# --- collections ---------------------------------------------------------------------------------------


async def _collection_read(db: Any, c: AssetCollection) -> CollectionRead:
    ids = list(
        (await db.execute(select(AssetCollectionMember.node_id).where(AssetCollectionMember.collection_id == c.id))).scalars()
    )
    return CollectionRead.model_validate(c).model_copy(update={"node_ids": ids})


@router.get(
    "/collections/",
    response_model=PaginatedListResponse[CollectionRead],
    summary="Job Packs, Shutdown Windows, Test Packs",
    dependencies=perm(P.READ),
)
async def collections(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    kind: Annotated[str | None, Query(max_length=30)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetCollection.project_id == project_id] + ([AssetCollection.kind == kind] if kind else [])
    total = await db.scalar(select(func.count()).select_from(AssetCollection).where(*where))
    rows = (
        await db.execute(
            select(AssetCollection)
            .where(*where)
            .order_by(AssetCollection.code)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = [(await _collection_read(db, c)).model_dump(mode="json") for c in rows]
    return paginated_response(crud_data={"data": data, "total_count": total or 0}, page=page, items_per_page=items_per_page)


@router.post(
    "/collections/", response_model=CollectionRead, status_code=201, summary="Create a Collection", dependencies=perm(P.CREATE)
)
async def create_collection(
    values: CollectionIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    c = AssetCollection(**values.model_dump())
    db.add(c)
    await db.commit()
    return await _collection_read(db, c)


@router.put(
    "/collections/{collection_id}/members",
    response_model=CollectionRead,
    summary="Set a Collection's Nodes",
    dependencies=perm(P.UPDATE),
)
async def set_members(
    collection_id: Id, values: MembersIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    c = await db.get(AssetCollection, collection_id)
    if c is None:
        raise service.NodeNotFound(str(collection_id))
    await readable_project(db, c.project_id, user["id"], held)
    valid = set(
        (
            await db.execute(
                select(AssetNode.id).where(AssetNode.project_id == c.project_id, AssetNode.id.in_(values.node_ids))
            )
        ).scalars()
    )
    await db.execute(delete(AssetCollectionMember).where(AssetCollectionMember.collection_id == c.id))
    db.add_all([AssetCollectionMember(collection_id=c.id, node_id=n) for n in sorted(valid)])
    await db.commit()
    return await _collection_read(db, c)
