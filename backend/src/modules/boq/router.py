"""Mounted at /api/v1/boq.

Bills are project data: every route that touches one reads its project through
``readable_project`` first. The resource catalog and assemblies are global, with optional
project-scoped entries (also checked through ``readable_project``).

Undo/redo is server-side: each change to a bill is logged with the rows it touched before and
after (see ``service.Change``), and ``POST /{boq_id}/undo`` and ``/redo`` replay the log, so cell
edits, inserts, deletes, moves, resource lines, markups and imports all undo the same way.
"""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import ConflictException, ForbiddenException, UnprocessableEntityException
from ...infrastructure.records import assert_transition, history_of, record_transition
from ...infrastructure.tabular import TableError, read_table, write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.models import Project
from ..projects.service import readable_project
from . import exchange, service
from .models import Assembly, Boq, Position, Resource
from .permissions import BoqPermissionName as P
from .schemas import (
    BoqApplyAssembly,
    BoqAssemblyIn,
    BoqAssemblyRead,
    BoqBulkRows,
    BoqCreate,
    BoqDetail,
    BoqImportReport,
    BoqLineIn,
    BoqLineUpdate,
    BoqPositionCreate,
    BoqPositionMove,
    BoqPositionUpdate,
    BoqResourceIn,
    BoqResourceRead,
    BoqResourceType,
    BoqResourceUpdate,
    BoqRuleset,
    BoqSummary,
    BoqTransition,
    BoqUpdate,
    BoqValidationReport,
)
from .validation import validate

router = APIRouter(tags=["Bill of Quantities"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
MAX_IMPORT_BYTES = 10 * 1024 * 1024
RESOURCE_FIELDS = ("code", "name", "type", "unit", "rate", "currency", "trade", "notes")
RESOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "code": ("code", "item code", "resource code", "article", "sku"),
    "name": ("name", "description", "resource", "text"),
    "type": ("type", "category", "kind"),
    "unit": ("unit", "uom"),
    "rate": ("rate", "price", "unit price", "cost", "unit rate"),
    "currency": ("currency", "cur"),
    "trade": ("trade", "craft"),
    "notes": ("notes", "productivity", "remarks", "comments"),
}


def perm(*names: P) -> list[Any]:
    return [require_permissions(*(n.value for n in names))]


async def _file(file: UploadFile) -> bytes:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise UnprocessableEntityException("Import files are limited to 10 MB.")
    return data


async def _boq(db: AsyncSession, boq_id: int, user: dict[str, Any], held: frozenset[str]) -> Boq:
    boq = await service.get_boq(db, boq_id)
    await readable_project(db, boq.project_id, user["id"], held)
    return boq


async def _position(db: AsyncSession, position_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[Boq, Position]:
    position = await service.get_position(db, position_id)
    return await _boq(db, position.boq_id, user, held), position


async def _detail(db: AsyncSession, boq: Boq) -> dict[str, Any]:
    return await service.detail(db, boq)


# --- resource catalog ---------------------------------------------------------------------------------------


@router.get(
    "/resources/",
    response_model=PaginatedListResponse[BoqResourceRead],
    summary="List Catalog Resources",
    description="The global catalog; with `project_id`, also the project's own resources, its overrides "
    "replacing the global entries they override.",
    dependencies=perm(P.READ),
)
async def list_resources(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    project_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    type: BoqResourceType | None = None,
    trade: Annotated[str | None, Query(max_length=60)] = None,
) -> Any:
    if project_id:
        await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [service.resource_scope(project_id)]
    if search:
        like = f"%{search.lower()}%"
        where.append(or_(func.lower(Resource.code).like(like), func.lower(Resource.name).like(like)))
    if type:
        where.append(Resource.type == type.value)
    if trade:
        where.append(func.lower(Resource.trade) == trade.lower())
    total = await db.scalar(select(func.count()).select_from(Resource).where(*where))
    rows = (
        await db.execute(
            select(Resource)
            .where(*where)
            .order_by(Resource.code, Resource.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_resources(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/resources/", response_model=BoqResourceRead, status_code=201, summary="Add a Resource", dependencies=perm(P.UPDATE)
)
async def create_resource(values: BoqResourceIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    if values.project_id:
        await readable_project(db, values.project_id, user["id"], held)
    await service.check_base(db, values.base_id, values.project_id)
    scope = Resource.project_id == values.project_id if values.project_id else Resource.project_id.is_(None)
    if await db.scalar(select(Resource.id).where(scope, func.lower(Resource.code) == values.code.lower()).limit(1)):
        raise ConflictException(f"The code {values.code} is already in this catalog.")
    fields = values.model_dump()
    fields["type"] = values.type.value
    resource = Resource(**fields)
    db.add(resource)
    await db.commit()
    return (await service.read_resources(db, [resource]))[0]


@router.post("/resources/import/preview", summary="Read a Resource Import File's Columns", dependencies=perm(P.IMPORT))
async def resources_import_preview(file: Annotated[UploadFile, File()], _: CurrentUserDep) -> dict[str, Any]:
    try:
        columns, rows = read_table(await _file(file), file.filename or "")
    except TableError as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    return {
        "columns": columns,
        "fields": list(RESOURCE_FIELDS),
        "mapping": _resource_mapping(columns),
        "sample": rows[:5],
        "rows": len(rows),
    }


def _resource_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    norm = {c: exchange._norm(c) for c in columns}
    for fld, aliases in RESOURCE_ALIASES.items():
        for column in columns:
            if norm[column] in aliases and column not in mapping.values():
                mapping[fld] = column
                break
    return mapping


@router.post(
    "/resources/import",
    response_model=BoqImportReport,
    summary="Import Resources from Excel or CSV",
    description="`mapping` is JSON `{field: column}`; leave it out to auto-detect. A row whose code is already "
    "in the same catalog (global, or the project's) updates that resource.",
    dependencies=perm(P.IMPORT),
)
async def import_resources(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form(max_length=4000)] = None,
    project_id: Annotated[int | None, Form(ge=1, le=MAX_INTEGER_ID)] = None,
    currency: Annotated[str, Form(pattern=r"^[A-Z]{3}$")] = "EUR",
) -> BoqImportReport:
    if project_id:
        await readable_project(db, project_id, user["id"], held)
    try:
        columns, rows = read_table(await _file(file), file.filename or "")
        parsed = json.loads(mapping) if mapping else _resource_mapping(columns)
    except (TableError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    if not isinstance(parsed, dict) or not set(parsed) <= set(RESOURCE_FIELDS):
        raise UnprocessableEntityException(f"mapping keys must be among {', '.join(RESOURCE_FIELDS)}")
    report = BoqImportReport(rows=len(rows), created=0, skipped=0, columns=columns)
    if "code" not in parsed or "name" not in parsed:
        report.errors.append("Map at least the code and name columns.")
        return report
    scope = Resource.project_id == project_id if project_id else Resource.project_id.is_(None)
    existing = {r.code.lower(): r for r in (await db.execute(select(Resource).where(scope))).scalars()}
    for line, row in enumerate(rows, start=2):
        value = {f: exchange._text(row.get(c)) for f, c in parsed.items()}
        code, name = value.get("code", "")[:40], value.get("name", "")[:300]
        if not code or not name:
            report.skipped += 1
            report.errors.append(f"Row {line}: no code or name")
            continue
        rate = exchange._number(value.get("rate"))
        if value.get("rate") and rate is None:
            report.errors.append(f"Row {line}: '{value['rate']}' isn't a rate")
        kind = value.get("type", "").lower()
        kind = {"labor": "labour", "plant": "equipment", "subcontractor": "subcontract"}.get(kind, kind)
        fields: dict[str, Any] = {
            "name": name,
            "unit": value.get("unit", "")[:20],
            "type": kind if kind in BoqResourceType._value2member_map_ else "material",
            "currency": (value.get("currency") or currency).upper()[:3],
            "trade": value.get("trade", "")[:60] or None,
            "notes": value.get("notes") or None,
        }
        if rate is not None:
            fields["rate"] = rate
        if code.lower() in existing:
            resource = existing[code.lower()]
            for k, v in fields.items():
                if v not in (None, ""):
                    setattr(resource, k, v)
        else:
            resource = Resource(code=code, project_id=project_id, **fields)
            db.add(resource)
            existing[code.lower()] = resource
            report.created += 1
    await db.commit()
    return report


@router.get("/resources/{resource_id}", response_model=BoqResourceRead, summary="Get a Resource", dependencies=perm(P.READ))
async def get_resource(resource_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    resource = await service.get_resource(db, resource_id)
    if resource.project_id:
        await readable_project(db, resource.project_id, user["id"], held)
    return (await service.read_resources(db, [resource]))[0]


@router.patch(
    "/resources/{resource_id}", response_model=BoqResourceRead, summary="Update a Resource", dependencies=perm(P.UPDATE)
)
async def update_resource(
    resource_id: Id, values: BoqResourceUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    resource = await service.get_resource(db, resource_id)
    if resource.project_id:
        await readable_project(db, resource.project_id, user["id"], held)
    for key, value in values.model_dump(exclude_unset=True).items():
        if value is None and key in ("code", "name", "type", "unit", "rate", "currency"):
            continue
        setattr(resource, key, value.value if hasattr(value, "value") else value)
    await db.commit()
    return (await service.read_resources(db, [resource]))[0]


@router.delete(
    "/resources/{resource_id}",
    summary="Delete a Resource",
    description="Positions and assemblies using it lose that resource line.",
    dependencies=perm(P.DELETE),
)
async def delete_resource(
    resource_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    resource = await service.get_resource(db, resource_id)
    if resource.project_id:
        await readable_project(db, resource.project_id, user["id"], held)
    await db.delete(resource)
    await db.commit()
    return {"message": "Resource deleted"}


# --- assemblies -------------------------------------------------------------------------------------------------


@router.get(
    "/assemblies/",
    response_model=PaginatedListResponse[BoqAssemblyRead],
    summary="List Assemblies",
    description="Global assemblies, plus the project's own with `project_id`.",
    dependencies=perm(P.READ),
)
async def list_assemblies(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    project_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    if project_id:
        await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [
        or_(Assembly.project_id.is_(None), Assembly.project_id == project_id) if project_id else Assembly.project_id.is_(None)
    ]
    if search:
        like = f"%{search.lower()}%"
        where.append(or_(func.lower(Assembly.code).like(like), func.lower(Assembly.name).like(like)))
    total = await db.scalar(select(func.count()).select_from(Assembly).where(*where))
    rows = (
        await db.execute(
            select(Assembly)
            .where(*where)
            .order_by(Assembly.code, Assembly.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_assemblies(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/assemblies/", response_model=BoqAssemblyRead, status_code=201, summary="Add an Assembly", dependencies=perm(P.UPDATE)
)
async def create_assembly(values: BoqAssemblyIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    if values.project_id:
        await readable_project(db, values.project_id, user["id"], held)
    assembly = Assembly(**values.model_dump(exclude={"lines"}))
    db.add(assembly)
    await db.flush()
    await service.save_assembly_lines(db, assembly, [line.model_dump() for line in values.lines])
    await db.commit()
    return (await service.read_assemblies(db, [assembly]))[0]


async def _assembly(db: AsyncSession, assembly_id: int, user: dict[str, Any], held: frozenset[str]) -> Assembly:
    assembly = await service.get_assembly(db, assembly_id)
    if assembly.project_id:
        await readable_project(db, assembly.project_id, user["id"], held)
    return assembly


@router.get("/assemblies/{assembly_id}", response_model=BoqAssemblyRead, summary="Get an Assembly", dependencies=perm(P.READ))
async def get_assembly(assembly_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return (await service.read_assemblies(db, [await _assembly(db, assembly_id, user, held)]))[0]


@router.put(
    "/assemblies/{assembly_id}",
    response_model=BoqAssemblyRead,
    summary="Replace an Assembly and its Lines",
    dependencies=perm(P.UPDATE),
)
async def update_assembly(
    assembly_id: Id, values: BoqAssemblyIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    assembly = await _assembly(db, assembly_id, user, held)
    if values.project_id and values.project_id != assembly.project_id:
        await readable_project(db, values.project_id, user["id"], held)
    for key, value in values.model_dump(exclude={"lines"}).items():
        setattr(assembly, key, value)
    await service.save_assembly_lines(db, assembly, [line.model_dump() for line in values.lines])
    await db.commit()
    return (await service.read_assemblies(db, [assembly]))[0]


@router.delete("/assemblies/{assembly_id}", summary="Delete an Assembly", dependencies=perm(P.DELETE))
async def delete_assembly(
    assembly_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await db.delete(await _assembly(db, assembly_id, user, held))
    await db.commit()
    return {"message": "Assembly deleted"}


# --- positions ---------------------------------------------------------------------------------------------------


@router.patch(
    "/positions/{position_id}",
    response_model=BoqDetail,
    summary="Edit a Position",
    description="Send `quantity_formula` (e.g. `2*3.5+1.2`) to set the quantity from it; an empty formula clears "
    "it. A position priced by resources takes its unit rate from them.",
    dependencies=perm(P.UPDATE),
)
async def update_position(
    position_id: Id, values: BoqPositionUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq, position = await _position(db, position_id, user, held)
    changes = values.model_dump(exclude_unset=True)
    if "short_text" in changes and changes["short_text"] is None:
        changes["short_text"] = ""
    if changes:
        await service.update_position(db, boq, position, changes, user["id"])
    return await _detail(db, boq)


@router.delete(
    "/positions/{position_id}",
    response_model=BoqDetail,
    summary="Delete a Row and Everything Below It",
    dependencies=perm(P.UPDATE),
)
async def delete_position(position_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    boq, position = await _position(db, position_id, user, held)
    await service.delete_position(db, boq, position, user["id"])
    return await _detail(db, boq)


@router.post(
    "/positions/{position_id}/move",
    response_model=BoqDetail,
    summary="Move a Row",
    description="Re-parent and reorder: the row (with everything below it) goes under `parent_id`, above "
    "`before_id`. Ordinals are renumbered.",
    dependencies=perm(P.UPDATE),
)
async def move_position(
    position_id: Id, values: BoqPositionMove, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq, position = await _position(db, position_id, user, held)
    await service.move_position(db, boq, position, values.parent_id, values.before_id, user["id"])
    return await _detail(db, boq)


@router.post(
    "/positions/{position_id}/resources",
    response_model=BoqDetail,
    status_code=201,
    summary="Price a Position with a Resource",
    description="The project's override of a global resource is used when there is one.",
    dependencies=perm(P.UPDATE),
)
async def add_line(
    position_id: Id, values: BoqLineIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq, position = await _position(db, position_id, user, held)
    await service.add_line(db, boq, position, values.model_dump(), user["id"])
    return await _detail(db, boq)


@router.patch(
    "/positions/{position_id}/resources/{line_id}",
    response_model=BoqDetail,
    summary="Change a Resource Line",
    dependencies=perm(P.UPDATE),
)
async def update_line(
    position_id: Id,
    line_id: Id,
    values: BoqLineUpdate,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    boq, position = await _position(db, position_id, user, held)
    line = await service.get_line(db, position, line_id)
    changes = values.model_dump(exclude_unset=True)
    for key in ("factor", "waste_pct"):
        if key in changes and changes[key] is None:
            del changes[key]
    await service.update_line(db, boq, position, line, changes, user["id"])
    return await _detail(db, boq)


@router.delete(
    "/positions/{position_id}/resources/{line_id}",
    response_model=BoqDetail,
    summary="Remove a Resource Line",
    dependencies=perm(P.UPDATE),
)
async def delete_line(
    position_id: Id, line_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq, position = await _position(db, position_id, user, held)
    line = await service.get_line(db, position, line_id)
    await service.delete_line(db, boq, position, line, user["id"])
    return await _detail(db, boq)


@router.post(
    "/positions/{position_id}/apply-assembly",
    response_model=BoqDetail,
    summary="Price a Position from an Assembly",
    description="Copies the assembly's resource lines into the position and keeps a link to the assembly.",
    dependencies=perm(P.UPDATE),
)
async def apply_assembly(
    position_id: Id, values: BoqApplyAssembly, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq, position = await _position(db, position_id, user, held)
    await service.apply_assembly(db, boq, position, values.assembly_id, values.replace, user["id"])
    return await _detail(db, boq)


# --- bills ---------------------------------------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedListResponse[BoqSummary],
    summary="List a Project's Bills",
    dependencies=perm(P.READ),
)
async def list_boqs(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    total = await db.scalar(select(func.count()).select_from(Boq).where(Boq.project_id == project_id))
    rows = (
        await db.execute(
            select(Boq)
            .where(Boq.project_id == project_id)
            .order_by(Boq.id)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [BoqSummary.model_validate(b).model_dump() for b in rows], "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=BoqDetail, status_code=201, summary="Start a Bill", dependencies=perm(P.CREATE))
async def create_boq(values: BoqCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await readable_project(db, values.project_id, user["id"], held)
    boq = Boq(
        project_id=project.id,
        name=values.name,
        description=values.description,
        currency=project.currency,
        created_by_id=user["id"],
    )
    db.add(boq)
    await db.flush()
    await record_transition(db, "boq", boq.id, None, "draft", user["id"])
    await db.commit()
    return await _detail(db, boq)


@router.get("/{boq_id}", response_model=BoqDetail, summary="A Bill with Every Row", dependencies=perm(P.READ))
async def get_boq(boq_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _detail(db, await _boq(db, boq_id, user, held))


@router.patch("/{boq_id}", response_model=BoqDetail, summary="Rename a Bill or Set its Markups", dependencies=perm(P.UPDATE))
async def update_boq(
    boq_id: Id, values: BoqUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq = await _boq(db, boq_id, user, held)
    changes = {k: v for k, v in values.model_dump(exclude_unset=True).items() if v is not None or k == "description"}
    if changes:
        await service.update_boq(db, boq, changes, user["id"])
    return await _detail(db, boq)


@router.delete("/{boq_id}", summary="Delete a Bill", dependencies=perm(P.DELETE))
async def delete_boq(boq_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    boq = await _boq(db, boq_id, user, held)
    service.assert_editable(boq)
    await db.delete(boq)
    await db.commit()
    return {"message": "Bill deleted"}


@router.post(
    "/{boq_id}/transition",
    response_model=BoqDetail,
    summary="Change a Bill's Status",
    description="draft ⇄ priced ⇄ locked. Locking and unlocking need `boq.approve`; a locked bill is read-only.",
    dependencies=perm(P.UPDATE),
)
async def transition(
    boq_id: Id, values: BoqTransition, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq = await _boq(db, boq_id, user, held)
    target = values.status.value
    assert_transition(service.FLOW, boq.status, target)
    if "locked" in (boq.status, target) and P.APPROVE.value not in held and not user.get("is_superuser"):
        raise ForbiddenException("Locking and unlocking a bill needs the boq.approve permission.")
    await record_transition(db, "boq", boq.id, boq.status, target, user["id"], values.note)
    boq.status = target
    await db.commit()
    return await _detail(db, boq)


@router.get("/{boq_id}/history", summary="A Bill's Status Changes", dependencies=perm(P.READ))
async def history(boq_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> list[dict[str, Any]]:
    await _boq(db, boq_id, user, held)
    return await history_of(db, "boq", boq_id)


@router.post("/{boq_id}/undo", response_model=BoqDetail, summary="Undo the Last Change", dependencies=perm(P.UPDATE))
async def undo(boq_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    boq = await _boq(db, boq_id, user, held)
    await service.undo(db, boq)
    return await _detail(db, boq)


@router.post("/{boq_id}/redo", response_model=BoqDetail, summary="Redo the Last Undone Change", dependencies=perm(P.UPDATE))
async def redo(boq_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    boq = await _boq(db, boq_id, user, held)
    await service.redo(db, boq)
    return await _detail(db, boq)


@router.post(
    "/{boq_id}/positions",
    response_model=BoqDetail,
    status_code=201,
    summary="Insert a Section or Position",
    description="Under `parent_id` (top level when left out), above `before_id` or below `after_id`, else last.",
    dependencies=perm(P.UPDATE),
)
async def create_position(
    boq_id: Id, values: BoqPositionCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq = await _boq(db, boq_id, user, held)
    row = values.model_dump(exclude={"parent_id", "before_id", "after_id"}, exclude_unset=True)
    row["kind"] = values.kind.value
    await service.create_positions(
        db,
        boq,
        values.parent_id,
        [row],
        before_id=values.before_id,
        after_id=values.after_id,
        user_id=user["id"],
        label=f"Insert {values.kind.value}",
    )
    return await _detail(db, boq)


@router.post(
    "/{boq_id}/positions/bulk",
    response_model=BoqDetail,
    status_code=201,
    summary="Insert Pasted Rows",
    description="Rows pasted from a spreadsheet become positions under `parent_id`, below `after_id`. One undo step.",
    dependencies=perm(P.UPDATE),
)
async def bulk_positions(
    boq_id: Id, values: BoqBulkRows, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    boq = await _boq(db, boq_id, user, held)
    rows = [{**r.model_dump(exclude_unset=True), "kind": "position"} for r in values.rows]
    await service.create_positions(
        db, boq, values.parent_id, rows, after_id=values.after_id, user_id=user["id"], label=f"Paste {len(rows)} rows"
    )
    return await _detail(db, boq)


@router.get(
    "/{boq_id}/validate",
    response_model=BoqValidationReport,
    summary="Check a Bill",
    description="Runs a rule set and scores the bill 0-100: `100 × max(0, 1 − Σweight / (10 × rows))` with "
    "error = 10, warning = 3, info = 1. Without `ruleset`, the project's classification standard's rule set "
    "(or `boq_quality`).",
    dependencies=perm(P.READ),
)
async def validate_boq(
    boq_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    ruleset: BoqRuleset | None = None,
) -> Any:
    boq = await _boq(db, boq_id, user, held)
    if ruleset is None:
        project = await db.get(Project, boq.project_id)
        standard = project.classification_standard if project else None
        ruleset = BoqRuleset(standard) if standard and standard in BoqRuleset._value2member_map_ else BoqRuleset.BOQ_QUALITY
    loaded = await service.load(db, boq.id)
    return validate(service.validation_bill(loaded), ruleset.value)


@router.post("/{boq_id}/import/preview", summary="Read an Import File's Columns", dependencies=perm(P.IMPORT))
async def import_preview(
    boq_id: Id, file: Annotated[UploadFile, File()], db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, Any]:
    await _boq(db, boq_id, user, held)
    try:
        columns, rows = read_table(await _file(file), file.filename or "")
    except TableError as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    return {
        "columns": columns,
        "fields": list(exchange.FIELDS),
        "mapping": exchange.auto_mapping(columns),
        "sample": rows[:5],
        "rows": len(rows),
    }


@router.post(
    "/{boq_id}/import",
    response_model=BoqImportReport,
    summary="Import Rows from Excel, CSV or GAEB XML",
    description="Spreadsheets: `mapping` is JSON `{field: column}` (fields: " + ", ".join(exchange.FIELDS) + "); "
    "the hierarchy comes from `level` (1 = top) or the ordinal's depth. GAEB DA XML (.x81-.x86, .xml) needs no "
    "mapping. `replace` swaps the bill's rows for the file's; otherwise they are appended. One undo step.",
    dependencies=perm(P.IMPORT),
)
async def import_boq(
    boq_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form(max_length=4000)] = None,
    replace: Annotated[bool, Form()] = False,
) -> BoqImportReport:
    boq = await _boq(db, boq_id, user, held)
    service.assert_editable(boq)
    data = await _file(file)
    name = (file.filename or "").lower()
    errors: list[str] = []
    columns: list[str] = []
    try:
        if name.endswith((".x81", ".x82", ".x83", ".x84", ".x85", ".x86", ".xml")):
            rows = exchange.rows_from_gaeb(data)
            total = len(rows)
        else:
            columns, table = read_table(data, file.filename or "")
            parsed = json.loads(mapping) if mapping else exchange.auto_mapping(columns)
            if not isinstance(parsed, dict) or not set(parsed) <= set(exchange.FIELDS):
                raise UnprocessableEntityException(f"mapping keys must be among {', '.join(exchange.FIELDS)}")
            unknown = [c for c in parsed.values() if c not in columns]
            if unknown:
                raise UnprocessableEntityException(f"Columns not in the file: {', '.join(map(str, unknown))}")
            rows, errors = exchange.rows_from_table(table, parsed)
            total = len(table)
    except (TableError, exchange.ImportError_, json.JSONDecodeError) as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    created = await service.import_rows(
        db, boq, rows, replace=replace, user_id=user["id"], label=f"Import {file.filename or 'file'}"[:200]
    )
    return BoqImportReport(rows=total, created=created, skipped=total - created, errors=errors, columns=columns)


@router.get(
    "/{boq_id}/export",
    summary="Download a Bill",
    description="`xlsx` (outline levels per depth, live formulas for totals and markups), `csv`, or GAEB DA XML "
    "`x83` (tender request, no prices) / `x84` (priced).",
    dependencies=perm(P.EXPORT),
)
async def export_boq(
    boq_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    format: Literal["xlsx", "csv", "x83", "x84"] = "xlsx",
) -> Response:
    boq = await _boq(db, boq_id, user, held)
    bill = await _detail(db, boq)
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in boq.name)[:60] or f"boq-{boq.id}"
    if format == "xlsx":
        body, media = exchange.to_xlsx(bill), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "csv":
        body, media, _ = write_table(exchange.CSV_COLUMNS, exchange.table_rows(bill), "csv")
    else:
        project = await db.get(Project, boq.project_id)
        body = exchange.to_gaeb(bill, project.name if project else "", phase=int(format[1:]))
        media = "application/xml"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{stem}.{format}"'})
