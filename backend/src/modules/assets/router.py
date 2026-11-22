"""Mounted at /api/v1/assets.

Project-scoped collections live under ``/{project_id}/<kind>/``; one row is changed at ``/<kind>/{id}``.
Every route checks the project's visibility through ``projects`` first.
"""

import json
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.records import history_of
from ...infrastructure.tabular import TableError, read_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import cobie, service
from .constants import ComponentStatus
from .importer import FIELDS, auto_mapping, run_import
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
from .permissions import AssetPermissionName as P
from .schemas import (
    AssetBulkResult,
    AssetComponentBulk,
    AssetComponentCreate,
    AssetComponentRead,
    AssetComponentUpdate,
    AssetFacilityCreate,
    AssetFacilityRead,
    AssetFacilityUpdate,
    AssetFloorCreate,
    AssetFloorRead,
    AssetFloorUpdate,
    AssetImportPreview,
    AssetImportReport,
    AssetSpaceCreate,
    AssetSpaceRead,
    AssetSpaceUpdate,
    AssetSystemCreate,
    AssetSystemRead,
    AssetSystemUpdate,
    AssetTree,
    AssetTypeCreate,
    AssetTypeRead,
    AssetTypeUpdate,
    AssetZoneCreate,
    AssetZoneRead,
    AssetZoneUpdate,
    CobieReport,
    ImportTarget,
)

router = APIRouter(tags=["Asset Register"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
Search = Annotated[str | None, Query(max_length=100)]
OptionalId = Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)]
MAX_IMPORT_BYTES = 10 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

Reader = Callable[[AsyncSession, list[Any]], Awaitable[list[dict[str, Any]]]]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _sync(fn: Callable[[list[Any]], list[dict[str, Any]]]) -> Reader:
    async def reader(_: AsyncSession, rows: list[Any]) -> list[dict[str, Any]]:
        return fn(rows)

    return reader


async def _page(
    db: AsyncSession, model: Any, where: list[Any], order: list[Any], page: int, per_page: int, reader: Reader
) -> Any:
    total = await db.scalar(select(func.count()).select_from(model).where(*where))
    rows = list(
        (
            await db.scalars(
                select(model).where(*where).order_by(*order).offset(compute_offset(page, per_page)).limit(per_page)
            )
        ).all()
    )
    return paginated_response(
        crud_data={"data": await reader(db, rows), "total_count": total or 0}, page=page, items_per_page=per_page
    )


def _search(model: Any, text: str | None) -> list[Any]:
    if not text:
        return []
    like = f"%{text.lower()}%"
    return [or_(func.lower(model.name).like(like), func.lower(func.coalesce(model.description, "")).like(like))]


async def _owned(db: AsyncSession, model: Any, row_id: int, user: dict[str, Any], held: frozenset[str]) -> Any:
    row = await service.get(db, model, row_id)
    await readable_project(db, row.project_id, user["id"], held)
    return row


# --- facilities -----------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/facilities/",
    response_model=PaginatedListResponse[AssetFacilityRead],
    summary="List Facilities",
    dependencies=perm(P.READ),
)
async def list_facilities(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = [AssetFacility.project_id == project_id]
    return await _page(db, AssetFacility, where, [AssetFacility.name], page, items_per_page, _sync(service.read_facilities))


@router.post(
    "/{project_id}/facilities/",
    response_model=AssetFacilityRead,
    status_code=201,
    summary="Add a Facility",
    dependencies=perm(P.CREATE),
)
async def create_facility(
    project_id: ProjectId, values: AssetFacilityCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    row = AssetFacility(project_id=project_id, **values.model_dump())
    db.add(row)
    await db.commit()
    return service.read_facilities([row])[0]


@router.patch(
    "/facilities/{row_id}", response_model=AssetFacilityRead, summary="Change a Facility", dependencies=perm(P.UPDATE)
)
async def update_facility(
    row_id: Id, values: AssetFacilityUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetFacility, row_id, user, held)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return service.read_facilities([row])[0]


@router.delete(
    "/facilities/{row_id}",
    summary="Delete a Facility",
    description="Its floors and spaces go too; their components stay, without a space.",
    dependencies=perm(P.DELETE),
)
async def delete_facility(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _owned(db, AssetFacility, row_id, user, held))
    await db.commit()
    return {"message": "Facility deleted"}


# --- floors ---------------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/floors/",
    response_model=PaginatedListResponse[AssetFloorRead],
    summary="List Floors",
    dependencies=perm(P.READ),
)
async def list_floors(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    facility_id: OptionalId = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetFloor.project_id == project_id]
    if facility_id:
        where.append(AssetFloor.facility_id == facility_id)
    order = [AssetFloor.position, AssetFloor.elevation, AssetFloor.name]
    return await _page(db, AssetFloor, where, order, page, items_per_page, _sync(service.read_floors))


@router.post(
    "/{project_id}/floors/", response_model=AssetFloorRead, status_code=201, summary="Add a Floor", dependencies=perm(P.CREATE)
)
async def create_floor(
    project_id: ProjectId, values: AssetFloorCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.in_project(db, AssetFacility, values.facility_id, project_id, "facility")
    row = AssetFloor(project_id=project_id, **values.model_dump())
    db.add(row)
    await db.commit()
    return service.read_floors([row])[0]


@router.patch("/floors/{row_id}", response_model=AssetFloorRead, summary="Change a Floor", dependencies=perm(P.UPDATE))
async def update_floor(
    row_id: Id, values: AssetFloorUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetFloor, row_id, user, held)
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    return service.read_floors([row])[0]


@router.delete(
    "/floors/{row_id}",
    summary="Delete a Floor",
    description="Its spaces go too; their components stay, without a space.",
    dependencies=perm(P.DELETE),
)
async def delete_floor(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _owned(db, AssetFloor, row_id, user, held))
    await db.commit()
    return {"message": "Floor deleted"}


# --- spaces ---------------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/spaces/",
    response_model=PaginatedListResponse[AssetSpaceRead],
    summary="List Spaces",
    dependencies=perm(P.READ),
)
async def list_spaces(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    floor_id: OptionalId = None,
    facility_id: OptionalId = None,
    search: Search = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetSpace.project_id == project_id, *_search(AssetSpace, search)]
    if floor_id:
        where.append(AssetSpace.floor_id == floor_id)
    if facility_id:
        where.append(AssetSpace.floor_id.in_(select(AssetFloor.id).where(AssetFloor.facility_id == facility_id)))
    return await _page(db, AssetSpace, where, [AssetSpace.name], page, items_per_page, service.read_spaces)


@router.post(
    "/{project_id}/spaces/", response_model=AssetSpaceRead, status_code=201, summary="Add a Space", dependencies=perm(P.CREATE)
)
async def create_space(
    project_id: ProjectId, values: AssetSpaceCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.in_project(db, AssetFloor, values.floor_id, project_id, "floor")
    row = AssetSpace(project_id=project_id, **values.model_dump())
    db.add(row)
    await db.commit()
    return (await service.read_spaces(db, [row]))[0]


@router.patch("/spaces/{row_id}", response_model=AssetSpaceRead, summary="Change a Space", dependencies=perm(P.UPDATE))
async def update_space(
    row_id: Id, values: AssetSpaceUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetSpace, row_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    if changes.get("floor_id"):
        await service.in_project(db, AssetFloor, changes["floor_id"], row.project_id, "floor")
    for key, value in changes.items():
        if key == "floor_id" and value is None:
            continue
        setattr(row, key, value)
    await db.commit()
    return (await service.read_spaces(db, [row]))[0]


@router.delete(
    "/spaces/{row_id}",
    summary="Delete a Space",
    description="Its components stay, without a space.",
    dependencies=perm(P.DELETE),
)
async def delete_space(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _owned(db, AssetSpace, row_id, user, held))
    await db.commit()
    return {"message": "Space deleted"}


# --- zones ----------------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/zones/", response_model=PaginatedListResponse[AssetZoneRead], summary="List Zones", dependencies=perm(P.READ)
)
async def list_zones(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = [AssetZone.project_id == project_id]
    return await _page(db, AssetZone, where, [AssetZone.name], page, items_per_page, _sync(service.read_zones))


@router.post(
    "/{project_id}/zones/", response_model=AssetZoneRead, status_code=201, summary="Add a Zone", dependencies=perm(P.CREATE)
)
async def create_zone(
    project_id: ProjectId, values: AssetZoneCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.check_spaces(db, project_id, values.space_ids)
    row = AssetZone(project_id=project_id, **values.model_dump())
    db.add(row)
    await db.commit()
    return service.read_zones([row])[0]


@router.patch("/zones/{row_id}", response_model=AssetZoneRead, summary="Change a Zone", dependencies=perm(P.UPDATE))
async def update_zone(
    row_id: Id, values: AssetZoneUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetZone, row_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    if "space_ids" in changes:
        await service.check_spaces(db, row.project_id, changes["space_ids"])
    for key, value in changes.items():
        setattr(row, key, value)
    await db.commit()
    return service.read_zones([row])[0]


@router.delete("/zones/{row_id}", summary="Delete a Zone", dependencies=perm(P.DELETE))
async def delete_zone(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _owned(db, AssetZone, row_id, user, held))
    await db.commit()
    return {"message": "Zone deleted"}


# --- types ----------------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/types/",
    response_model=PaginatedListResponse[AssetTypeRead],
    summary="List Product Types",
    dependencies=perm(P.READ),
)
async def list_types(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    search: Search = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = [AssetType.project_id == project_id, *_search(AssetType, search)]
    return await _page(db, AssetType, where, [AssetType.name], page, items_per_page, service.read_types)


@router.post(
    "/{project_id}/types/",
    response_model=AssetTypeRead,
    status_code=201,
    summary="Add a Product Type",
    dependencies=perm(P.CREATE),
)
async def create_type(
    project_id: ProjectId, values: AssetTypeCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.check_contact(db, values.manufacturer_id)
    await service.check_contact(db, values.warranty_guarantor_id)
    row = AssetType(project_id=project_id, **values.model_dump(mode="python"))
    db.add(row)
    await db.commit()
    return (await service.read_types(db, [row]))[0]


@router.patch("/types/{row_id}", response_model=AssetTypeRead, summary="Change a Product Type", dependencies=perm(P.UPDATE))
async def update_type(
    row_id: Id, values: AssetTypeUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetType, row_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    await service.check_contact(db, changes.get("manufacturer_id"))
    await service.check_contact(db, changes.get("warranty_guarantor_id"))
    for key, value in changes.items():
        setattr(row, key, value)
    await db.commit()
    return (await service.read_types(db, [row]))[0]


@router.delete(
    "/types/{row_id}",
    summary="Delete a Product Type",
    description="Its components stay, without a type.",
    dependencies=perm(P.DELETE),
)
async def delete_type(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _owned(db, AssetType, row_id, user, held))
    await db.commit()
    return {"message": "Type deleted"}


# --- systems --------------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/systems/",
    response_model=PaginatedListResponse[AssetSystemRead],
    summary="List Systems",
    dependencies=perm(P.READ),
)
async def list_systems(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    search: Search = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = [AssetSystem.project_id == project_id, *_search(AssetSystem, search)]
    return await _page(db, AssetSystem, where, [AssetSystem.name], page, items_per_page, service.read_systems)


@router.post(
    "/{project_id}/systems/",
    response_model=AssetSystemRead,
    status_code=201,
    summary="Add a System",
    dependencies=perm(P.CREATE),
)
async def create_system(
    project_id: ProjectId, values: AssetSystemCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await service.check_components(db, project_id, values.component_ids)
    row = AssetSystem(project_id=project_id, **values.model_dump(exclude={"component_ids"}))
    db.add(row)
    await db.flush()
    await service.set_system_components(db, row.id, values.component_ids)
    await db.commit()
    return (await service.read_systems(db, [row]))[0]


@router.patch("/systems/{row_id}", response_model=AssetSystemRead, summary="Change a System", dependencies=perm(P.UPDATE))
async def update_system(
    row_id: Id, values: AssetSystemUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetSystem, row_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    members = changes.pop("component_ids", None)
    for key, value in changes.items():
        setattr(row, key, value)
    if members is not None:
        await service.check_components(db, row.project_id, members)
        await service.set_system_components(db, row.id, members)
    await db.commit()
    return (await service.read_systems(db, [row]))[0]


@router.delete("/systems/{row_id}", summary="Delete a System", dependencies=perm(P.DELETE))
async def delete_system(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    await db.delete(await _owned(db, AssetSystem, row_id, user, held))
    await db.commit()
    return {"message": "System deleted"}


# --- components -----------------------------------------------------------------------------------------


@router.get(
    "/{project_id}/components/",
    response_model=PaginatedListResponse[AssetComponentRead],
    summary="List Components",
    description="Filter by where they are (facility, floor, space, or `unplaced`), type, system, status or text.",
    dependencies=perm(P.READ),
)
async def list_components(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    facility_id: OptionalId = None,
    floor_id: OptionalId = None,
    space_id: OptionalId = None,
    unplaced: bool = False,
    type_id: OptionalId = None,
    system_id: OptionalId = None,
    status: ComponentStatus | None = None,
    search: Search = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetComponent.project_id == project_id]
    if space_id:
        where.append(AssetComponent.space_id == space_id)
    elif floor_id:
        where.append(AssetComponent.space_id.in_(select(AssetSpace.id).where(AssetSpace.floor_id == floor_id)))
    elif facility_id:
        where.append(
            AssetComponent.space_id.in_(
                select(AssetSpace.id)
                .join(AssetFloor, AssetFloor.id == AssetSpace.floor_id)
                .where(AssetFloor.facility_id == facility_id)
            )
        )
    if unplaced:
        where.append(AssetComponent.space_id.is_(None))
    if type_id:
        where.append(AssetComponent.type_id == type_id)
    if system_id:
        where.append(
            AssetComponent.id.in_(select(AssetSystemComponent.component_id).where(AssetSystemComponent.system_id == system_id))
        )
    if status:
        where.append(AssetComponent.status == status.value)
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                *(
                    func.lower(func.coalesce(col, "")).like(like)
                    for col in (
                        AssetComponent.name,
                        AssetComponent.description,
                        AssetComponent.serial_number,
                        AssetComponent.tag_number,
                        AssetComponent.bar_code,
                        AssetComponent.asset_identifier,
                    )
                )
            )
        )
    return await _page(db, AssetComponent, where, [AssetComponent.name], page, items_per_page, service.read_components)


@router.post(
    "/{project_id}/components/",
    response_model=AssetComponentRead,
    status_code=201,
    summary="Add a Component",
    dependencies=perm(P.CREATE),
)
async def create_component(
    project_id: ProjectId, values: AssetComponentCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    fields = values.model_dump(exclude={"system_ids"})
    await service.check_component_links(db, project_id, {**fields, "system_ids": values.system_ids})
    row = AssetComponent(project_id=project_id, **{**fields, "status": values.status.value})
    db.add(row)
    await db.flush()
    await service.set_component_systems(db, row.id, values.system_ids)
    await db.commit()
    return (await service.read_components(db, [row]))[0]


@router.post(
    "/{project_id}/components/bulk",
    response_model=AssetBulkResult,
    status_code=201,
    summary="Add Many Components",
    description="One component per name, sharing a type, space and status. Names already in the register are skipped.",
    dependencies=perm(P.CREATE),
)
async def bulk_components(
    project_id: ProjectId, values: AssetComponentBulk, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> AssetBulkResult:
    await readable_project(db, project_id, user["id"], held)
    await service.check_component_links(db, project_id, {"type_id": values.type_id, "space_id": values.space_id})
    existing = await service.existing_names(db, AssetComponent, project_id)
    created: list[AssetComponent] = []
    skipped: list[str] = []
    for raw in values.names:
        name = raw.strip()
        if not name:
            continue
        if name.lower() in existing:
            skipped.append(name)
            continue
        row = AssetComponent(
            project_id=project_id, name=name, type_id=values.type_id, space_id=values.space_id, status=values.status.value
        )
        db.add(row)
        existing[name.lower()] = row
        created.append(row)
    await db.commit()
    return AssetBulkResult(
        created=[AssetComponentRead(**c) for c in await service.read_components(db, created)], skipped=skipped
    )


@router.get("/components/{row_id}", response_model=AssetComponentRead, summary="Get a Component", dependencies=perm(P.READ))
async def get_component(row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_components(db, [await _owned(db, AssetComponent, row_id, user, held)]))[0]


@router.patch(
    "/components/{row_id}",
    response_model=AssetComponentRead,
    summary="Change a Component",
    description="A status change follows planned → installed → commissioned → in service → decommissioned "
    "and is recorded in the history.",
    dependencies=perm(P.UPDATE),
)
async def update_component(
    row_id: Id, values: AssetComponentUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    row = await _owned(db, AssetComponent, row_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    systems = changes.pop("system_ids", None)
    status = changes.pop("status", None)
    note = changes.pop("status_note", None)
    await service.check_component_links(db, row.project_id, {**changes, "system_ids": systems or []})
    for key, value in changes.items():
        setattr(row, key, value)
    if status is not None:
        await service.change_status(db, row, ComponentStatus(status).value, user["id"], note)
    if systems is not None:
        await service.set_component_systems(db, row.id, systems)
    await db.commit()
    return (await service.read_components(db, [row]))[0]


@router.get("/components/{row_id}/history", summary="A Component's Status History", dependencies=perm(P.READ))
async def component_history(
    row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    await _owned(db, AssetComponent, row_id, user, held)
    return await history_of(db, "asset", row_id)


@router.delete("/components/{row_id}", summary="Delete a Component", dependencies=perm(P.DELETE))
async def delete_component(
    row_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await db.delete(await _owned(db, AssetComponent, row_id, user, held))
    await db.commit()
    return {"message": "Component deleted"}


# --- tree, import, COBie --------------------------------------------------------------------------------


@router.get(
    "/{project_id}/tree",
    response_model=AssetTree,
    summary="Facility → Floor → Space Tree",
    description="With the number of components in each.",
    dependencies=perm(P.READ),
)
async def tree(project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> AssetTree:
    await readable_project(db, project_id, user["id"], held)
    return await service.tree(db, project_id)


async def _read_upload(file: UploadFile) -> tuple[list[str], list[dict[str, Any]]]:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise UnprocessableEntityException("Import files are limited to 10 MB.")
    try:
        return read_table(data, file.filename or "")
    except TableError as exc:
        raise UnprocessableEntityException(str(exc)) from exc


@router.post(
    "/{project_id}/import/preview",
    response_model=AssetImportPreview,
    summary="Read an Import File's Columns",
    dependencies=perm(P.IMPORT),
)
async def import_preview(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    target: Annotated[ImportTarget, Form()] = "components",
) -> AssetImportPreview:
    await readable_project(db, project_id, user["id"], held)
    columns, rows = await _read_upload(file)
    return AssetImportPreview(
        target=target,
        columns=columns,
        fields=list(FIELDS[target]),
        mapping=auto_mapping(target, columns),
        sample=[{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in rows[:5]],
        rows=len(rows),
    )


@router.post(
    "/{project_id}/import",
    response_model=AssetImportReport,
    summary="Import Components or Types",
    description="`mapping` is JSON `{field: column}`; leave it out to auto-detect. `dry_run` reports without writing. "
    "`extra_as_attributes` keeps unmapped columns as attributes.",
    dependencies=perm(P.IMPORT),
)
async def import_rows(
    project_id: ProjectId,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    target: Annotated[ImportTarget, Form()] = "components",
    mapping: Annotated[str | None, Form(max_length=4000)] = None,
    on_duplicate: Annotated[Literal["skip", "update"], Form()] = "skip",
    dry_run: Annotated[bool, Form()] = False,
    extra_as_attributes: Annotated[bool, Form()] = False,
) -> AssetImportReport:
    await readable_project(db, project_id, user["id"], held)
    columns, rows = await _read_upload(file)
    try:
        parsed = json.loads(mapping) if mapping else None
    except json.JSONDecodeError as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    if parsed is not None and not (
        isinstance(parsed, dict) and set(parsed) <= set(FIELDS[target]) and all(isinstance(v, str) for v in parsed.values())
    ):
        raise UnprocessableEntityException(f"mapping keys must be among {', '.join(FIELDS[target])}")
    return await run_import(
        db,
        project_id,
        target,
        columns,
        rows,
        parsed,
        on_duplicate=on_duplicate,
        dry_run=dry_run,
        extra_as_attributes=extra_as_attributes,
    )


@router.get(
    "/{project_id}/cobie.xlsx",
    summary="COBie Workbook",
    description="COBie 2.4 sheets Contact, Facility, Floor, Space, Zone, Type, Component, System, Document, Attribute.",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}},
    dependencies=perm(P.EXPORT),
)
async def cobie_export(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    register = await cobie.load(db, project)
    body = cobie.workbook(cobie.build_rows(register, user.get("email") or f"user-{user['id']}@unknown.invalid"))
    filename = f"{project.code}-COBie.xlsx"
    return Response(body, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get(
    "/{project_id}/cobie/validate",
    response_model=CobieReport,
    summary="Check the Register Against COBie",
    description="Missing required fields, missing references and duplicate names, per sheet.",
    dependencies=perm(P.READ),
)
async def cobie_validate(
    project_id: ProjectId, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> CobieReport:
    project = await readable_project(db, project_id, user["id"], held)
    return cobie.validate(await cobie.load(db, project))
