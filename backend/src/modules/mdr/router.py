"""Mounted at /api/v1/mdr."""

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import FileResponse
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import NotFoundException, UnprocessableEntityException
from ...infrastructure.records import NumberingError, history_of, link_allocation, next_number
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..files.models import StoredFile
from ..files.storage import storage
from ..projects.service import readable_project
from . import override, override_router, service
from .constants import ENTITY, DossierStatus, RevisionStatus
from .gate import ready
from .models import MdrDossier, MdrRevision
from .permissions import MdrPermissionName as P
from .schemas import (
    CatalogueRead,
    DecisionIn,
    DossierIn,
    DossierRead,
    DossierUpdate,
    GateRead,
    HashCheckIn,
    HashCheckRead,
    IssueIn,
    RevisionRead,
    SignIn,
)

router = APIRouter(tags=["MDR / turnover dossiers"])
router.include_router(override_router.router)

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


async def _dossier(db: Any, dossier_id: int, user: dict[str, Any], held: frozenset[str]) -> MdrDossier:
    dossier = await service.get_dossier(db, dossier_id)
    await readable_project(db, dossier.project_id, user["id"], held)
    return dossier


async def _revision(db: Any, revision_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[MdrRevision, MdrDossier]:
    revision, dossier = await service.get_revision(db, revision_id)
    await readable_project(db, dossier.project_id, user["id"], held)
    return revision, dossier


async def _dossier_read(db: Any, dossier: MdrDossier) -> dict[str, Any]:
    return (
        DossierRead.model_validate(dossier)
        .model_copy(update={"scope_labels": await service.scope_labels(db, dossier)})
        .model_dump(mode="json")
    )


async def _revision_reads(db: Any, revisions: list[MdrRevision]) -> list[dict[str, Any]]:
    names = await service.user_names(db, {i for r in revisions for i in (r.compiled_by_id, r.signed_by_id, r.decided_by_id)})
    return [
        RevisionRead.model_validate(r)
        .model_copy(
            update={
                "compiled_by_name": names.get(r.compiled_by_id or 0),
                "signed_by_name": names.get(r.signed_by_id or 0),
                "decided_by_name": names.get(r.decided_by_id or 0),
            }
        )
        .model_dump(mode="json")
        for r in revisions
    ]


@router.get(
    "/sections", response_model=list[CatalogueRead], summary="Sections and Who Provides Them", dependencies=perm(P.READ)
)
async def sections(
    project_id: Annotated[int, Query(ge=1)], db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return await service.catalogue(db, project_id)


@router.get(
    "/dossiers/", response_model=PaginatedListResponse[DossierRead], summary="A Project's Dossiers", dependencies=perm(P.READ)
)
async def list_dossiers(
    project_id: Annotated[int, Query(ge=1)],
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = MdrDossier.project_id == project_id
    total = await db.scalar(select(func.count()).select_from(MdrDossier).where(where))
    rows = (
        await db.execute(
            select(MdrDossier)
            .where(where)
            .order_by(MdrDossier.code)
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = [await _dossier_read(db, d) for d in rows]
    return paginated_response(crud_data={"data": data, "total_count": total or 0}, page=page, items_per_page=items_per_page)


@router.post("/dossiers/", response_model=DossierRead, status_code=201, summary="Define a Dossier", dependencies=perm(P.CREATE))
async def create_dossier(values: DossierIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    await service.check_scope(db, values.project_id, values.scope_node_ids, values.scope_collection_ids)
    sections = service.normalise_sections([s.model_dump() for s in values.sections] if values.sections is not None else None)
    try:
        code = await next_number(
            db, "mdr", values.project_id, fallback_prefix="MDR", values=values.number_values, user_id=user["id"]
        )
    except NumberingError as exc:
        raise UnprocessableEntityException("; ".join(exc.problems)) from exc
    dossier = MdrDossier(
        project_id=values.project_id,
        code=code,
        title=values.title,
        description=values.description,
        scope_node_ids=values.scope_node_ids,
        scope_collection_ids=values.scope_collection_ids,
        sections=sections,
        created_by_id=user["id"],
    )
    db.add(dossier)
    await db.flush()
    await link_allocation(db, values.project_id, "mdr", code, (ENTITY, dossier.id))
    await record_audit(
        db,
        "mdr.dossier.created",
        ENTITY,
        dossier.id,
        actor_id=user["id"],
        project_id=dossier.project_id,
        summary=f"{code} {dossier.title}",
        after={"scope_node_ids": dossier.scope_node_ids, "scope_collection_ids": dossier.scope_collection_ids},
    )
    await db.commit()
    return await _dossier_read(db, dossier)


@router.get("/dossiers/{dossier_id}", response_model=DossierRead, summary="Get a Dossier", dependencies=perm(P.READ))
async def get_dossier(dossier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await _dossier_read(db, await _dossier(db, dossier_id, user, held))


@router.patch(
    "/dossiers/{dossier_id}",
    response_model=DossierRead,
    summary="Change a Dossier's Title, Scope or Sections",
    description="Applies to the next compile; issued revisions keep what they were compiled from.",
    dependencies=perm(P.UPDATE),
)
async def update_dossier(
    dossier_id: Id, values: DossierUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    data = values.model_dump(exclude_unset=True)
    if "scope_node_ids" in data or "scope_collection_ids" in data:
        await service.check_scope(
            db, dossier.project_id, data.get("scope_node_ids") or [], data.get("scope_collection_ids") or []
        )
    if "sections" in data:
        data["sections"] = service.normalise_sections(data["sections"])
    for key, value in data.items():
        if value is None and key in ("title", "scope_node_ids", "scope_collection_ids", "sections"):
            continue
        setattr(dossier, key, value)
    await db.commit()
    return await _dossier_read(db, dossier)


@router.delete(
    "/dossiers/{dossier_id}",
    summary="Delete a Dossier Never Issued",
    description="A dossier with an issued revision can't be deleted.",
    dependencies=perm(P.DELETE),
)
async def delete_dossier(
    dossier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    dossier = await _dossier(db, dossier_id, user, held)
    if await db.scalar(
        select(MdrRevision.id).where(MdrRevision.dossier_id == dossier.id, MdrRevision.revision.is_not(None)).limit(1)
    ):
        raise UnprocessableEntityException("The dossier has issued revisions and is kept for the record.")
    await record_audit(
        db, "mdr.dossier.deleted", ENTITY, dossier.id, actor_id=user["id"], project_id=dossier.project_id, summary=dossier.code
    )
    await db.delete(dossier)
    await db.commit()
    return {"message": "Dossier deleted"}


@router.get(
    "/dossiers/{dossier_id}/gate",
    response_model=GateRead,
    summary="Readiness Checks (Dry Run)",
    description="The same checks an issue runs. Checks whose module is absent or off report `not_available`.",
    dependencies=perm(P.READ),
)
async def dossier_gate(
    dossier_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    purpose: Annotated[str | None, Query(pattern="^(review|final)$")] = None,
) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    checks = await service.gate(db, dossier, purpose)
    return {"purpose": purpose, "ready": ready(checks), "checks": checks, "counts": await override.gate_counts(db, dossier)}


@router.post(
    "/dossiers/{dossier_id}/draft",
    response_model=RevisionRead,
    summary="Compile a Draft",
    description="Compiles whatever the gate says (open findings are listed on the cover), stamps every page DRAFT, "
    "and replaces the previous draft.",
    dependencies=perm(P.SUBMIT),
)
async def draft(dossier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    revision = await service.compile_draft(db, dossier, user["id"])
    await db.commit()
    return (await _revision_reads(db, [revision]))[0]


@router.post(
    "/dossiers/{dossier_id}/issue",
    response_model=RevisionRead,
    status_code=201,
    summary="Issue a Revision",
    description="`review` issues Rev A, B ... for the client; `final` issues Rev 0, 1 ... once the client accepted a "
    "review revision. Runs the gate (422 listing what blocks), compiles and stamps; the revision then needs signing.",
    dependencies=perm(P.SUBMIT),
)
async def issue(dossier_id: Id, values: IssueIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    revision = await service.issue(db, dossier, values.purpose.value, values.note, user["id"])
    await db.commit()
    return (await _revision_reads(db, [revision]))[0]


@router.get(
    "/dossiers/{dossier_id}/revisions",
    response_model=list[RevisionRead],
    summary="Drafts and Revisions",
    dependencies=perm(P.READ),
)
async def revisions(dossier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    rows = list(
        (
            await db.execute(select(MdrRevision).where(MdrRevision.dossier_id == dossier.id).order_by(MdrRevision.id.desc()))
        ).scalars()
    )
    return await _revision_reads(db, rows)


@router.get("/dossiers/{dossier_id}/history", summary="Status History", dependencies=perm(P.READ))
async def history(
    dossier_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    dossier = await _dossier(db, dossier_id, user, held)
    return await history_of(db, ENTITY, dossier.id)


@router.post(
    "/dossiers/{dossier_id}/verify-hash",
    response_model=HashCheckRead,
    summary="Check a Copy Against the Stored Hashes",
    description="Send the SHA-256 the browser computed of a copy you hold (the file itself is never uploaded).",
    dependencies=perm(P.READ),
)
async def verify_hash(
    dossier_id: Id, values: HashCheckIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    dossier = await _dossier(db, dossier_id, user, held)
    return await service.verify_hash(db, dossier, values.sha256)


@router.post(
    "/revisions/{revision_id}/sign",
    response_model=RevisionRead,
    summary="Sign an Issued Revision",
    description="Appends the signer's attestation to the stamped file, then stores the SHA-256 of the final bytes.",
    dependencies=perm(P.SIGN),
)
async def sign(
    revision_id: Id, values: SignIn, request: Request, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    if not values.confirm:
        raise UnprocessableEntityException("Confirm the intent statement to sign.")
    revision, dossier = await _revision(db, revision_id, user, held)
    if dossier.status == DossierStatus.FINAL and revision.kind == "review":
        raise UnprocessableEntityException("The dossier is final.")
    await service.sign(db, revision, dossier, user, request.client.host if request.client else None)
    await db.commit()
    return (await _revision_reads(db, [revision]))[0]


@router.post(
    "/revisions/{revision_id}/decision",
    response_model=RevisionRead,
    summary="The Client Accepts or Rejects a Review Revision",
    dependencies=perm(P.ACCEPT),
)
async def decision(
    revision_id: Id, values: DecisionIn, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    revision, dossier = await _revision(db, revision_id, user, held)
    await service.decide(db, revision, dossier, values.decision.value, values.note, user["id"])
    await db.commit()
    return (await _revision_reads(db, [revision]))[0]


@router.get(
    "/revisions/{revision_id}/download",
    summary="Download a Compiled Revision",
    description="`unsigned=true` gives the stamped file before signing.",
    dependencies=perm(P.READ),
)
async def download(
    revision_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, unsigned: bool = False
) -> FileResponse:
    revision, dossier = await _revision(db, revision_id, user, held)
    if revision.status == RevisionStatus.PENDING_SIGNATURE and not unsigned:
        unsigned = True
    file_id = revision.unsigned_file_id if unsigned else revision.file_id
    stored = await db.get(StoredFile, file_id) if file_id else None
    if stored is None:
        raise NotFoundException("The compiled file is missing")
    return FileResponse(
        storage().path(stored.storage_key),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(stored.name)}",
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": stored.sha256,
        },
    )
