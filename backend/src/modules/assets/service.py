"""Reading and writing the register. Callers check project visibility first."""

from collections import defaultdict
from typing import Any, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.records import assert_transition, record_transition
from ..common.exceptions import ResourceNotFoundError
from ..contacts.models import Contact
from ..contacts.service import contact_names
from ..files.models import StoredFile
from .constants import COMPONENT_FLOW, ENTITY_COMPONENT
from .models import (
    AssetComponent,
    AssetFacility,
    AssetFloor,
    AssetSpace,
    AssetSystem,
    AssetSystemComponent,
    AssetType,
    AssetZone,
)
from .schemas import (
    AssetComponentRead,
    AssetFacilityRead,
    AssetFloorRead,
    AssetSpaceRead,
    AssetSystemRead,
    AssetTree,
    AssetTreeFacility,
    AssetTreeFloor,
    AssetTreeSpace,
    AssetTypeRead,
    AssetZoneRead,
)

Row = TypeVar("Row", AssetFacility, AssetFloor, AssetSpace, AssetZone, AssetType, AssetComponent, AssetSystem)


class AssetNotFoundError(ResourceNotFoundError):
    public_detail = "Not found in the asset register."


async def get(db: AsyncSession, model: type[Row], row_id: int) -> Row:
    row = await db.get(model, row_id)
    if row is None:
        raise AssetNotFoundError(f"No {model.__tablename__} {row_id}")
    return row


async def in_project(db: AsyncSession, model: type[Row], row_id: int | None, project_id: int, label: str) -> Row | None:
    """The row, which must belong to the project; ``None`` passes through."""
    if row_id is None:
        return None
    row = await db.get(model, row_id)
    if row is None or row.project_id != project_id:
        raise UnprocessableEntityException(f"That {label} isn't in this project.")
    return row


async def check_contact(db: AsyncSession, contact_id: int | None) -> None:
    if contact_id is not None and await db.get(Contact, contact_id) is None:
        raise UnprocessableEntityException("No such contact.")


async def check_spaces(db: AsyncSession, project_id: int, ids: list[int]) -> None:
    if not ids:
        return
    found = set(
        (await db.scalars(select(AssetSpace.id).where(AssetSpace.id.in_(ids), AssetSpace.project_id == project_id))).all()
    )
    if found != set(ids):
        raise UnprocessableEntityException("Some spaces aren't in this project.")


async def check_components(db: AsyncSession, project_id: int, ids: list[int]) -> None:
    if not ids:
        return
    found = set(
        (
            await db.scalars(
                select(AssetComponent.id).where(AssetComponent.id.in_(ids), AssetComponent.project_id == project_id)
            )
        ).all()
    )
    if found != set(ids):
        raise UnprocessableEntityException("Some components aren't in this project.")


async def check_systems(db: AsyncSession, project_id: int, ids: list[int]) -> None:
    if not ids:
        return
    found = set(
        (await db.scalars(select(AssetSystem.id).where(AssetSystem.id.in_(ids), AssetSystem.project_id == project_id))).all()
    )
    if found != set(ids):
        raise UnprocessableEntityException("Some systems aren't in this project.")


# --- reading --------------------------------------------------------------------------------------------


def _dump(schema: Any, row: Any, **extra: Any) -> dict[str, Any]:
    dumped: dict[str, Any] = schema.model_validate(row).model_copy(update=extra).model_dump(mode="json")
    return dumped


def read_facilities(rows: list[AssetFacility]) -> list[dict[str, Any]]:
    return [_dump(AssetFacilityRead, r) for r in rows]


def read_floors(rows: list[AssetFloor]) -> list[dict[str, Any]]:
    return [_dump(AssetFloorRead, r) for r in rows]


def read_zones(rows: list[AssetZone]) -> list[dict[str, Any]]:
    return [_dump(AssetZoneRead, r) for r in rows]


async def read_spaces(db: AsyncSession, rows: list[AssetSpace]) -> list[dict[str, Any]]:
    ids = [r.id for r in rows]
    counts: dict[int, int] = {}
    if ids:
        result = await db.execute(
            select(AssetComponent.space_id, func.count())
            .where(AssetComponent.space_id.in_(ids))
            .group_by(AssetComponent.space_id)
        )
        counts = {sid: n for sid, n in result.tuples().all() if sid is not None}
    return [_dump(AssetSpaceRead, r, component_count=counts.get(r.id, 0)) for r in rows]


async def read_types(db: AsyncSession, rows: list[AssetType]) -> list[dict[str, Any]]:
    ids = [r.id for r in rows]
    counts: dict[int, int] = {}
    if ids:
        result = await db.execute(
            select(AssetComponent.type_id, func.count()).where(AssetComponent.type_id.in_(ids)).group_by(AssetComponent.type_id)
        )
        counts = {tid: n for tid, n in result.tuples().all() if tid is not None}
    names = await contact_names(db, {c for r in rows for c in (r.manufacturer_id, r.warranty_guarantor_id) if c})
    return [
        _dump(
            AssetTypeRead,
            r,
            component_count=counts.get(r.id, 0),
            manufacturer_name=names.get(r.manufacturer_id) if r.manufacturer_id else None,
            warranty_guarantor_name=names.get(r.warranty_guarantor_id) if r.warranty_guarantor_id else None,
        )
        for r in rows
    ]


async def system_members(db: AsyncSession, system_ids: list[int]) -> dict[int, list[int]]:
    members: dict[int, list[int]] = defaultdict(list)
    if system_ids:
        result = await db.execute(
            select(AssetSystemComponent.system_id, AssetSystemComponent.component_id)
            .where(AssetSystemComponent.system_id.in_(system_ids))
            .order_by(AssetSystemComponent.component_id)
        )
        for sid, cid in result.tuples().all():
            members[sid].append(cid)
    return members


async def read_systems(db: AsyncSession, rows: list[AssetSystem]) -> list[dict[str, Any]]:
    members = await system_members(db, [r.id for r in rows])
    return [_dump(AssetSystemRead, r, component_ids=members[r.id]) for r in rows]


async def read_components(db: AsyncSession, rows: list[AssetComponent]) -> list[dict[str, Any]]:
    ids = [r.id for r in rows]
    type_ids = {r.type_id for r in rows if r.type_id}
    space_ids = {r.space_id for r in rows if r.space_id}
    types = (
        dict((await db.execute(select(AssetType.id, AssetType.name).where(AssetType.id.in_(type_ids)))).tuples().all())
        if type_ids
        else {}
    )
    spaces: dict[int, tuple[str, int, str, int]] = {}
    if space_ids:
        result = await db.execute(
            select(AssetSpace.id, AssetSpace.name, AssetFloor.id, AssetFloor.name, AssetFloor.facility_id)
            .join(AssetFloor, AssetFloor.id == AssetSpace.floor_id)
            .where(AssetSpace.id.in_(space_ids))
        )
        spaces = {sid: (sname, fid, fname, fac) for sid, sname, fid, fname, fac in result.tuples().all()}
    systems: dict[int, list[int]] = defaultdict(list)
    documents: dict[int, int] = {}
    if ids:
        links = await db.execute(
            select(AssetSystemComponent.component_id, AssetSystemComponent.system_id).where(
                AssetSystemComponent.component_id.in_(ids)
            )
        )
        for cid, sid in links.tuples().all():
            systems[cid].append(sid)
        docs = await db.execute(
            select(StoredFile.entity_id, func.count())
            .where(StoredFile.entity_type == ENTITY_COMPONENT, StoredFile.entity_id.in_(ids), StoredFile.is_latest.is_(True))
            .group_by(StoredFile.entity_id)
        )
        documents = {eid: n for eid, n in docs.tuples().all() if eid is not None}
    out = []
    for r in rows:
        space = spaces.get(r.space_id) if r.space_id else None
        out.append(
            _dump(
                AssetComponentRead,
                r,
                type_name=types.get(r.type_id) if r.type_id else None,
                space_name=space[0] if space else None,
                floor_id=space[1] if space else None,
                floor_name=space[2] if space else None,
                facility_id=space[3] if space else None,
                system_ids=sorted(systems[r.id]),
                document_count=documents.get(r.id, 0),
            )
        )
    return out


async def tree(db: AsyncSession, project_id: int) -> AssetTree:
    facilities = (
        await db.scalars(select(AssetFacility).where(AssetFacility.project_id == project_id).order_by(AssetFacility.name))
    ).all()
    floors = (
        await db.scalars(
            select(AssetFloor)
            .where(AssetFloor.project_id == project_id)
            .order_by(AssetFloor.position, AssetFloor.elevation, AssetFloor.name)
        )
    ).all()
    spaces = (await db.scalars(select(AssetSpace).where(AssetSpace.project_id == project_id).order_by(AssetSpace.name))).all()
    counts = dict(
        (
            await db.execute(
                select(AssetComponent.space_id, func.count())
                .where(AssetComponent.project_id == project_id)
                .group_by(AssetComponent.space_id)
            )
        )
        .tuples()
        .all()
    )
    by_floor: dict[int, list[AssetTreeSpace]] = defaultdict(list)
    for s in spaces:
        by_floor[s.floor_id].append(
            AssetTreeSpace(id=s.id, name=s.name, category=s.category, component_count=counts.get(s.id, 0))
        )
    by_facility: dict[int, list[AssetTreeFloor]] = defaultdict(list)
    for f in floors:
        children = by_floor[f.id]
        by_facility[f.facility_id].append(
            AssetTreeFloor(
                id=f.id,
                name=f.name,
                elevation=f.elevation,
                component_count=sum(c.component_count for c in children),
                spaces=children,
            )
        )
    return AssetTree(
        facilities=[
            AssetTreeFacility(
                id=fac.id,
                name=fac.name,
                component_count=sum(f.component_count for f in by_facility[fac.id]),
                floors=by_facility[fac.id],
            )
            for fac in facilities
        ],
        unplaced_components=counts.get(None, 0),
    )


# --- writing --------------------------------------------------------------------------------------------


async def set_component_systems(db: AsyncSession, component_id: int, system_ids: list[int]) -> None:
    await db.execute(delete(AssetSystemComponent).where(AssetSystemComponent.component_id == component_id))
    for sid in dict.fromkeys(system_ids):
        db.add(AssetSystemComponent(system_id=sid, component_id=component_id))


async def set_system_components(db: AsyncSession, system_id: int, component_ids: list[int]) -> None:
    await db.execute(delete(AssetSystemComponent).where(AssetSystemComponent.system_id == system_id))
    for cid in dict.fromkeys(component_ids):
        db.add(AssetSystemComponent(system_id=system_id, component_id=cid))


async def check_component_links(db: AsyncSession, project_id: int, values: dict[str, Any]) -> None:
    if "type_id" in values:
        await in_project(db, AssetType, values["type_id"], project_id, "type")
    if "space_id" in values:
        await in_project(db, AssetSpace, values["space_id"], project_id, "space")
    if values.get("system_ids"):
        await check_systems(db, project_id, values["system_ids"])


async def change_status(db: AsyncSession, component: AssetComponent, target: str, user_id: int, note: str | None) -> None:
    if target == component.status:
        return
    assert_transition(COMPONENT_FLOW, component.status, target)
    await record_transition(db, "asset", component.id, component.status, target, user_id, note)
    component.status = target


async def existing_names(db: AsyncSession, model: Any, project_id: int) -> dict[str, Any]:
    """``{lower name: row}`` for a project's rows of one kind."""
    rows = (await db.scalars(select(model).where(model.project_id == project_id))).all()
    return {r.name.lower(): r for r in rows}
