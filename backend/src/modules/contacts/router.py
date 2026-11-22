"""Mounted at /api/v1/contacts."""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import delete

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ...infrastructure.tabular import TableError, read_table, write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import ContactType
from .importer import FIELDS, auto_mapping, run_import
from .models import Company, Contact, ProjectContact
from .permissions import ContactPermissionName as P
from .schemas import CompanyIn, CompanyRead, ContactIn, ContactRead, ImportReport, ProjectLinkSet

router = APIRouter(tags=["Contacts"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
MAX_IMPORT_BYTES = 10 * 1024 * 1024


def perm(*names: P) -> list[Any]:
    return [require_permissions(*(n.value for n in names))]


@router.get("/", response_model=PaginatedListResponse[ContactRead], summary="List Contacts", dependencies=perm(P.READ))
async def list_contacts(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
    search: Annotated[str | None, Query(max_length=100)] = None,
    type: ContactType | None = None,
    company_id: Annotated[int | None, Query(ge=1)] = None,
    project_id: Annotated[int | None, Query(ge=1)] = None,
    tag: Annotated[str | None, Query(max_length=50)] = None,
) -> Any:
    data = await service.page(
        db,
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        search=search,
        type_=type.value if type else None,
        company_id=company_id,
        project_id=project_id,
        tag=tag,
    )
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=ContactRead, status_code=201, summary="Create a Contact", dependencies=perm(P.CREATE))
async def create_contact(values: ContactIn, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    if values.company_id:
        await service.get_company(db, values.company_id)
    contact = Contact(**values.model_dump())
    db.add(contact)
    await db.commit()
    return (await service.read_contacts(db, [contact]))[0]


# --- companies (before /{contact_id} so the path isn't read as an id) ---------------------------------


@router.get(
    "/companies/", response_model=PaginatedListResponse[CompanyRead], summary="List Companies", dependencies=perm(P.READ)
)
async def list_companies(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    data = await service.companies_page(db, skip=compute_offset(page, items_per_page), limit=items_per_page, search=search)
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/companies/", response_model=CompanyRead, status_code=201, summary="Create a Company", dependencies=perm(P.CREATE)
)
async def create_company(values: CompanyIn, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    company = Company(**values.model_dump())
    db.add(company)
    await db.commit()
    return CompanyRead.model_validate(company)


@router.put("/companies/{company_id}", response_model=CompanyRead, summary="Update a Company", dependencies=perm(P.UPDATE))
async def update_company(company_id: Id, values: CompanyIn, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    company = await service.get_company(db, company_id)
    for key, value in values.model_dump().items():
        setattr(company, key, value)
    await db.commit()
    return CompanyRead.model_validate(company)


@router.delete(
    "/companies/{company_id}",
    summary="Delete a Company",
    description="Its contacts stay, without a company.",
    dependencies=perm(P.DELETE),
)
async def delete_company(company_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> dict[str, str]:
    await db.delete(await service.get_company(db, company_id))
    await db.commit()
    return {"message": "Company deleted"}


# --- project links ------------------------------------------------------------------------------------


@router.put(
    "/projects/{project_id}/{contact_id}",
    response_model=ContactRead,
    summary="Link a Contact to a Project, with a Role",
    dependencies=perm(P.UPDATE),
)
async def link_project(
    project_id: Id,
    contact_id: Id,
    values: ProjectLinkSet,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    contact = await service.get_contact(db, contact_id)
    link = await db.get(ProjectContact, (project_id, contact_id))
    if link is None:
        db.add(ProjectContact(project_id=project_id, contact_id=contact_id, role=values.role))
    else:
        link.role = values.role
    await db.commit()
    return (await service.read_contacts(db, [contact]))[0]


@router.delete("/projects/{project_id}/{contact_id}", summary="Unlink a Contact from a Project", dependencies=perm(P.UPDATE))
async def unlink_project(project_id: Id, contact_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> dict[str, str]:
    await db.execute(
        delete(ProjectContact).where(ProjectContact.project_id == project_id, ProjectContact.contact_id == contact_id)
    )
    await db.commit()
    return {"message": "Unlinked"}


# --- import -------------------------------------------------------------------------------------------


@router.post("/import/preview", summary="Read an Import File's Columns", dependencies=perm(P.IMPORT))
async def import_preview(file: Annotated[UploadFile, File()], _: CurrentUserDep) -> dict[str, Any]:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise UnprocessableEntityException("Import files are limited to 10 MB.")
    try:
        columns, rows = read_table(data, file.filename or "")
    except TableError as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    return {"columns": columns, "fields": list(FIELDS), "mapping": auto_mapping(columns), "sample": rows[:5], "rows": len(rows)}


@router.post(
    "/import",
    response_model=ImportReport,
    summary="Bulk Import Contacts",
    description="`mapping` is JSON `{field: column}`; leave it out to auto-detect. `dry_run` reports without writing.",
    dependencies=perm(P.IMPORT),
)
async def import_contacts(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form(max_length=4000)] = None,
    on_duplicate: Annotated[Literal["skip", "update"], Form()] = "skip",
    dry_run: Annotated[bool, Form()] = False,
    project_id: Annotated[int | None, Form(ge=1)] = None,
    project_role: Annotated[str | None, Form(max_length=150)] = None,
) -> ImportReport:
    if project_id:
        await readable_project(db, project_id, user["id"], held)
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise UnprocessableEntityException("Import files are limited to 10 MB.")
    try:
        columns, rows = read_table(data, file.filename or "")
        parsed = json.loads(mapping) if mapping else None
    except (TableError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityException(str(exc)) from exc
    if parsed is not None and not (isinstance(parsed, dict) and set(parsed) <= set(FIELDS)):
        raise UnprocessableEntityException(f"mapping keys must be among {', '.join(FIELDS)}")
    return await run_import(
        db, columns, rows, parsed, on_duplicate=on_duplicate, dry_run=dry_run, project_id=project_id, project_role=project_role
    )


EXPORT_COLUMNS = [
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("company_name", "Company"),
    ("type", "Type"),
    ("job_title", "Job title"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("mobile", "Mobile"),
    ("tags", "Tags"),
    ("project_roles", "Projects"),
    ("notes", "Notes"),
]


@router.get(
    "/export",
    summary="Export Contacts",
    description="The directory, with the same filters as the list, as Excel or CSV.",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}},
    dependencies=perm(P.READ),
)
async def export_contacts(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    format: Literal["xlsx", "csv"] = "xlsx",
    search: Annotated[str | None, Query(max_length=100)] = None,
    type: ContactType | None = None,
    company_id: Annotated[int | None, Query(ge=1)] = None,
    project_id: Annotated[int | None, Query(ge=1)] = None,
    tag: Annotated[str | None, Query(max_length=50)] = None,
) -> Response:
    data = await service.page(
        db,
        skip=0,
        limit=50_000,
        search=search,
        type_=type.value if type else None,
        company_id=company_id,
        project_id=project_id,
        tag=tag,
    )
    rows = [
        {
            **c,
            "project_roles": "; ".join(p["project_code"] + (f" ({p['role']})" if p["role"] else "") for p in c["projects"]),
        }
        for c in data["data"]
    ]
    body, media_type, ext = write_table(EXPORT_COLUMNS, rows, format, title="Contacts")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="contacts.{ext}"'})


# --- one contact ----------------------------------------------------------------------------------------


@router.get("/{contact_id}", response_model=ContactRead, summary="Get a Contact", dependencies=perm(P.READ))
async def get_contact(contact_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    return (await service.read_contacts(db, [await service.get_contact(db, contact_id)]))[0]


@router.put("/{contact_id}", response_model=ContactRead, summary="Update a Contact", dependencies=perm(P.UPDATE))
async def update_contact(contact_id: Id, values: ContactIn, db: AsyncSessionDep, _: CurrentUserDep) -> Any:
    contact = await service.get_contact(db, contact_id)
    if values.company_id:
        await service.get_company(db, values.company_id)
    for key, value in values.model_dump().items():
        setattr(contact, key, value)
    await db.commit()
    return (await service.read_contacts(db, [contact]))[0]


@router.delete("/{contact_id}", summary="Delete a Contact", dependencies=perm(P.DELETE))
async def delete_contact(contact_id: Id, db: AsyncSessionDep, _: CurrentUserDep) -> dict[str, str]:
    await db.delete(await service.get_contact(db, contact_id))
    await db.commit()
    return {"message": "Contact deleted"}


@router.get("/lookup/names", summary="Names for Contact Ids", dependencies=perm(P.READ))
async def names(db: AsyncSessionDep, _: CurrentUserDep, ids: Annotated[list[int], Query(max_length=200)]) -> dict[int, str]:
    return await service.contact_names(db, set(ids))
