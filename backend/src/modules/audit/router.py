"""Mounted at /api/v1/audit. Read-only: nothing here ever changes a ledger entry."""

import json
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from ...infrastructure.audit_ledger import AuditEntry, verify_chain
from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.tabular import write_table
from ..common.pagination import ItemsPerPageDep, PageDep
from ..projects.service import readable_project, visible_project_ids
from ..user.models import User
from .permissions import AuditPermissionName as P

router = APIRouter(tags=["Audit ledger"])

MAX_EXPORT = 50_000


class AuditEntryRead(BaseModel):
    seq: int
    created_at: datetime
    actor_id: int | None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: str | None
    project_id: int | None
    summary: str | None
    before: Any = None
    after: Any = None
    prev_hash: str
    hash: str


class ChainVerifyRead(BaseModel):
    ok: bool
    length: int
    head_hash: str
    first_broken_seq: int | None
    problem: str | None


async def _filters(
    db: Any,
    user: dict[str, Any],
    held: frozenset[str],
    *,
    entity_type: str | None,
    entity_id: str | None,
    actor_id: int | None,
    project_id: int | None,
    action: str | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
) -> list[Any]:
    where: list[Any] = []
    if project_id is not None:
        await readable_project(db, project_id, user["id"], held)
        where.append(AuditEntry.project_id == project_id)
    elif "projects.read" not in held and not user.get("is_superuser"):
        # Without staff-wide project access only the entries of visible projects are shown.
        where.append(AuditEntry.project_id.in_(await visible_project_ids(db, user["id"], held)))
    if entity_type:
        where.append(AuditEntry.entity_type == entity_type)
    if entity_id:
        where.append(AuditEntry.entity_id == entity_id)
    if actor_id:
        where.append(AuditEntry.actor_id == actor_id)
    if action:
        where.append(AuditEntry.action.like(f"{action}%"))
    if date_from:
        where.append(AuditEntry.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        where.append(AuditEntry.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(func.lower(func.coalesce(AuditEntry.summary, "")).like(like), func.lower(AuditEntry.action).like(like))
        )
    return where


async def _reads(db: Any, rows: list[AuditEntry]) -> list[dict[str, Any]]:
    ids = {r.actor_id for r in rows if r.actor_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all()) if ids else {}
    return [
        AuditEntryRead.model_validate(r, from_attributes=True)
        .model_copy(update={"actor_name": names.get(r.actor_id) if r.actor_id else None})
        .model_dump(mode="json")
        for r in rows
    ]


EntityType = Annotated[str | None, Query(max_length=40)]
EntityId = Annotated[str | None, Query(max_length=80)]
ActorId = Annotated[int | None, Query(ge=1)]
ProjectId = Annotated[int | None, Query(ge=1)]
Action = Annotated[str | None, Query(max_length=80, description="Prefix, e.g. `mdr.` or `asset_tree.node.`")]
Search = Annotated[str | None, Query(max_length=100)]


@router.get(
    "/entries/",
    response_model=PaginatedListResponse[AuditEntryRead],
    summary="Browse the Ledger",
    description="Newest first. Filter by entity, actor, project, action prefix and date range.",
    dependencies=[require_permissions(P.READ.value)],
)
async def entries(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    entity_type: EntityType = None,
    entity_id: EntityId = None,
    actor_id: ActorId = None,
    project_id: ProjectId = None,
    action: Action = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Search = None,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 50,
) -> Any:
    where = await _filters(
        db,
        user,
        held,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        project_id=project_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    total = await db.scalar(select(func.count()).select_from(AuditEntry).where(*where))
    rows = (
        await db.execute(
            select(AuditEntry)
            .where(*where)
            .order_by(AuditEntry.seq.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    return paginated_response(
        crud_data={"data": await _reads(db, list(rows)), "total_count": total or 0}, page=page, items_per_page=items_per_page
    )


@router.get(
    "/verify",
    response_model=ChainVerifyRead,
    summary="Verify the Chain",
    description="Recomputes every entry's hash and link from the first entry; reports the first broken link.",
    dependencies=[require_permissions(P.READ.value)],
)
async def verify(db: AsyncSessionDep, _: CurrentUserDep) -> ChainVerifyRead:
    report = await verify_chain(db)
    return ChainVerifyRead(
        ok=report.ok,
        length=report.length,
        head_hash=report.head_hash,
        first_broken_seq=report.first_broken_seq,
        problem=report.problem,
    )


COLUMNS = [
    ("seq", "Seq"),
    ("created_at", "When (UTC)"),
    ("actor_name", "Actor"),
    ("action", "Action"),
    ("entity_type", "Entity"),
    ("entity_id", "Entity id"),
    ("project_id", "Project"),
    ("summary", "Summary"),
    ("before", "Before"),
    ("after", "After"),
    ("hash", "Hash"),
]


@router.get(
    "/export",
    summary="Export the Filtered Ledger",
    description="Excel or CSV with every column, hashes included, so the chain can be checked offline.",
    dependencies=[require_permissions(P.EXPORT.value)],
)
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    format: Literal["xlsx", "csv"] = "xlsx",
    entity_type: EntityType = None,
    entity_id: EntityId = None,
    actor_id: ActorId = None,
    project_id: ProjectId = None,
    action: Action = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Search = None,
) -> Response:
    where = await _filters(
        db,
        user,
        held,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        project_id=project_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    rows = list((await db.execute(select(AuditEntry).where(*where).order_by(AuditEntry.seq).limit(MAX_EXPORT))).scalars())
    data = await _reads(db, rows)
    for row in data:
        for key in ("before", "after"):
            row[key] = "" if row[key] is None else json.dumps(row[key], sort_keys=True, ensure_ascii=False)
    body, media_type, ext = write_table(COLUMNS, data, format, title="Audit ledger")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="audit-ledger.{ext}"'})
