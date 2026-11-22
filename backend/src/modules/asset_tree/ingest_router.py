"""Terminology, the ingestion wizard and mapping profiles. Included in ``router.py`` under /api/v1/asset-tree."""

import json
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Path, Query, UploadFile
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import NotFoundException, UnprocessableEntityException
from ...infrastructure.tabular import TableError, read_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import ingest, terminology
from .models import AssetLevel, AssetMappingProfile
from .permissions import AssetTreePermissionName as P
from .schemas import (
    AssetTermRead,
    AssetTermsIn,
    MappingProfileIn,
    MappingProfileRead,
    TreeImportMapping,
    TreeImportPreview,
    TreeImportReport,
)

router = APIRouter(tags=["Asset hierarchy"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
ProjectQ = Annotated[int, Query(ge=1)]
MAX_IMPORT_BYTES = 10 * 1024 * 1024


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


# --- terminology ---------------------------------------------------------------------------------------


@router.get(
    "/terminology",
    response_model=list[AssetTermRead],
    summary="The Project's Terminology",
    description="Level labels and domain nouns with singular and plural forms, project overrides applied.",
    dependencies=perm(P.READ),
)
async def get_terminology(project_id: ProjectQ, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await terminology.resolved(db, project_id)


@router.put(
    "/terminology",
    response_model=list[AssetTermRead],
    summary="Override Terms",
    description="`null` clears an override, so the level label or built-in default applies again.",
    dependencies=perm(P.CONFIGURE),
)
async def put_terminology(
    values: AssetTermsIn, project_id: ProjectQ, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    await terminology.set_terms(
        db, project_id, {k: (v.model_dump() if v is not None else None) for k, v in values.terms.items()}
    )
    await db.commit()
    return await terminology.resolved(db, project_id)


# --- import --------------------------------------------------------------------------------------------


async def _read_upload(file: UploadFile) -> tuple[list[str], list[dict[str, Any]]]:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise UnprocessableEntityException("Import files are limited to 10 MB.")
    try:
        return read_table(data, file.filename or "")
    except TableError as exc:
        raise UnprocessableEntityException(str(exc)) from exc


async def _profile(db: AsyncSession, project_id: int, profile_id: int) -> AssetMappingProfile:
    profile = await db.get(AssetMappingProfile, profile_id)
    if profile is None or profile.project_id != project_id:
        raise NotFoundException("Mapping profile not found.")
    return profile


def _mapping(text: str) -> TreeImportMapping:
    try:
        return TreeImportMapping.model_validate(json.loads(text))
    except (json.JSONDecodeError, PydanticValidationError) as exc:
        raise UnprocessableEntityException(f"The mapping isn't valid: {exc}") from exc


def _plain(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    return str(value)


@router.post(
    "/import/preview",
    response_model=TreeImportPreview,
    summary="Read an Import File",
    description="The file's columns, a sample, and a first mapping guessed from the headers "
    "(or the chosen profile's mapping, with the columns this file lacks).",
    dependencies=perm(P.IMPORT),
)
async def import_preview(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    profile_id: Annotated[int | None, Form(ge=1, le=MAX_INTEGER_ID)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    columns, rows = await _read_upload(file)
    if profile_id:
        mapping = TreeImportMapping.model_validate((await _profile(db, project_id, profile_id)).mapping)
    else:
        levels = list(
            (
                await db.execute(
                    select(AssetLevel).where(AssetLevel.project_id == project_id).order_by(AssetLevel.depth, AssetLevel.id)
                )
            ).scalars()
        )
        try:
            mapping = ingest.guess_mapping(columns, levels)
        except PydanticValidationError:  # nothing recognisable: an empty columns-mode guess
            mapping = TreeImportMapping.model_construct()
    return TreeImportPreview(
        columns=columns,
        rows=len(rows),
        sample=[{k: _plain(v) for k, v in r.items()} for r in rows[:10]],
        mapping=mapping,
        missing=ingest.missing_columns(mapping, ingest.Columns(columns, mapping.synonyms)),
    )


@router.post(
    "/import",
    response_model=TreeImportReport,
    summary="Import Breakdown Rows",
    description="`mapping` is an `TreeImportMapping` as JSON, or give `profile_id`. `dry_run` (the default) reports what "
    "would be created and updated, row errors and warnings, and writes nothing; otherwise the good rows are written in "
    "one transaction. `save_profile_as` saves the mapping as a new version of that profile when the import is applied.",
    dependencies=perm(P.IMPORT),
)
async def import_rows(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form(max_length=20000)] = None,
    profile_id: Annotated[int | None, Form(ge=1, le=MAX_INTEGER_ID)] = None,
    dry_run: Annotated[bool, Form()] = True,
    save_profile_as: Annotated[str | None, Form(min_length=1, max_length=120)] = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    if mapping:
        spec = _mapping(mapping)
    elif profile_id:
        spec = TreeImportMapping.model_validate((await _profile(db, project_id, profile_id)).mapping)
    else:
        raise UnprocessableEntityException("Give a mapping or a mapping profile.")
    columns, rows = await _read_upload(file)
    report = await ingest.run_import(db, project_id, spec, columns, rows, dry_run)
    result = TreeImportReport.model_validate(report, from_attributes=True)
    if save_profile_as and not dry_run:
        profile = await _save_profile(db, project_id, save_profile_as, spec, user["id"])
        await db.commit()
        result.profile = MappingProfileRead.model_validate(profile)
    return result


# --- mapping profiles ----------------------------------------------------------------------------------


async def _save_profile(
    db: AsyncSession, project_id: int, name: str, mapping: TreeImportMapping, user_id: int
) -> AssetMappingProfile:
    latest = await db.scalar(
        select(func.max(AssetMappingProfile.version)).where(
            AssetMappingProfile.project_id == project_id, AssetMappingProfile.name == name
        )
    )
    profile = AssetMappingProfile(
        project_id=project_id,
        name=name,
        version=(latest or 0) + 1,
        mapping=mapping.model_dump(mode="json"),
        created_by_id=user_id,
    )
    db.add(profile)
    await db.flush()
    return profile


@router.get(
    "/mapping-profiles/",
    response_model=PaginatedListResponse[MappingProfileRead],
    summary="Import Mapping Profiles",
    description="The latest version of each profile, or every version of one with `name`.",
    dependencies=perm(P.READ),
)
async def list_profiles(
    project_id: ProjectQ,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    name: Annotated[str | None, Query(max_length=120)] = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [AssetMappingProfile.project_id == project_id]
    if name:
        where.append(AssetMappingProfile.name == name)
    else:
        latest = (
            select(AssetMappingProfile.name, func.max(AssetMappingProfile.version).label("v"))
            .where(AssetMappingProfile.project_id == project_id)
            .group_by(AssetMappingProfile.name)
            .subquery()
        )
        where.append(
            AssetMappingProfile.id.in_(
                select(AssetMappingProfile.id).join(
                    latest, (latest.c.name == AssetMappingProfile.name) & (latest.c.v == AssetMappingProfile.version)
                )
            )
        )
    total = await db.scalar(select(func.count()).select_from(AssetMappingProfile).where(*where))
    rows = (
        await db.execute(
            select(AssetMappingProfile)
            .where(*where)
            .order_by(AssetMappingProfile.name, AssetMappingProfile.version.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = [MappingProfileRead.model_validate(p).model_dump(mode="json") for p in rows]
    return paginated_response(crud_data={"data": data, "total_count": total or 0}, page=page, items_per_page=items_per_page)


@router.post(
    "/mapping-profiles/",
    response_model=MappingProfileRead,
    status_code=201,
    summary="Save a Mapping Profile",
    description="Saving under an existing name adds a new version.",
    dependencies=perm(P.IMPORT),
)
async def save_profile(values: MappingProfileIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    profile = await _save_profile(db, values.project_id, values.name, values.mapping, user["id"])
    await db.commit()
    return profile


@router.get(
    "/mapping-profiles/{profile_id}",
    response_model=MappingProfileRead,
    summary="Get a Mapping Profile",
    dependencies=perm(P.READ),
)
async def get_profile(profile_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    profile = await db.get(AssetMappingProfile, profile_id)
    if profile is None:
        raise NotFoundException("Mapping profile not found.")
    await readable_project(db, profile.project_id, user["id"], held)
    return profile


@router.delete(
    "/mapping-profiles/{profile_id}",
    summary="Delete a Mapping Profile (every version)",
    dependencies=perm(P.IMPORT),
)
async def delete_profile(
    profile_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    profile = await db.get(AssetMappingProfile, profile_id)
    if profile is None:
        raise NotFoundException("Mapping profile not found.")
    await readable_project(db, profile.project_id, user["id"], held)
    for p in (
        await db.execute(
            select(AssetMappingProfile).where(
                AssetMappingProfile.project_id == profile.project_id, AssetMappingProfile.name == profile.name
            )
        )
    ).scalars():
        await db.delete(p)
    await db.commit()
    return {"message": "Mapping profile deleted"}
