"""Client plan review routes, under /api/v1/portal/reviews."""

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Path, Query
from fastapi.responses import FileResponse
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.records import history_of
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..files.storage import storage
from ..projects.service import readable_project
from . import review_service as service
from .models import PlanReview
from .permissions import PortalPermissionName as P
from .review_schemas import (
    DocumentDecision,
    PlanReviewCreate,
    PlanReviewDetail,
    PlanReviewRead,
    PlanReviewUpdate,
    ReviewCommentCreate,
    ReviewDocumentAdd,
    ReviewShare,
)

review_router = APIRouter(prefix="/reviews", tags=["Client Plan Review"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


@review_router.get(
    "/",
    response_model=PaginatedListResponse[PlanReviewRead],
    summary="Plan Reviews",
    description="Staff see every review of the project; a client sees the ones shared with their client team "
    "(their review queue: `status=shared`).",
    dependencies=perm(P.READ),
)
async def list_reviews(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: Literal["draft", "shared", "reviewed", "withdrawn"] | None = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where: list[Any] = [PlanReview.project_id == project_id, *service.visibility_filter(user, held)]
    if status:
        where.append(PlanReview.status == status)
    total = await db.scalar(select(func.count()).select_from(PlanReview).where(*where))
    rows = (
        await db.execute(
            select(PlanReview)
            .where(*where)
            .order_by(PlanReview.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_reviews(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@review_router.post(
    "/",
    response_model=PlanReviewDetail,
    status_code=201,
    summary="Prepare a Plan Review",
    description="A draft package of the project's files; nothing reaches the client until it is shared.",
    dependencies=perm(P.SUBMIT),
)
async def create_review(
    values: PlanReviewCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    review = await service.create(db, values.model_dump(), user["id"])
    return await service.detail(db, review, user, held)


@review_router.get("/{review_id}", response_model=PlanReviewDetail, summary="A Plan Review", dependencies=perm(P.READ))
async def get_review(review_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    return await service.detail(db, review, user, held)


@review_router.patch(
    "/{review_id}", response_model=PlanReviewDetail, summary="Change a Plan Review", dependencies=perm(P.SUBMIT)
)
async def update_review(
    review_id: Id, values: PlanReviewUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    for key, value in values.model_dump(exclude_unset=True).items():
        if value is None and key in {"title", "kind"}:
            continue
        setattr(review, key, value)
    await db.commit()
    return await service.detail(db, review, user, held)


@review_router.get("/{review_id}/history", summary="Status History", dependencies=perm(P.READ))
async def review_history(
    review_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> list[dict[str, Any]]:
    review = await service.visible_review(db, review_id, user, held)
    return await history_of(db, service.ENTITY, review.id)


@review_router.post(
    "/{review_id}/documents",
    response_model=PlanReviewDetail,
    summary="Add a Document",
    description="On a shared or reviewed package the new document goes to the client for a decision.",
    dependencies=perm(P.SUBMIT),
)
async def add_document(
    review_id: Id, values: ReviewDocumentAdd, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    await service.add_document(db, review, values.file_id, values.title, user["id"])
    return await service.detail(db, review, user, held)


@review_router.post(
    "/{review_id}/share",
    response_model=PlanReviewDetail,
    summary="Share with the Client",
    description="Notifies every member of the client team.",
    dependencies=perm(P.SUBMIT),
)
async def share(
    review_id: Id, values: ReviewShare, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    await service.share(db, review, values.note, user["id"])
    return await service.detail(db, review, user, held)


@review_router.post("/{review_id}/withdraw", response_model=PlanReviewDetail, summary="Withdraw", dependencies=perm(P.SUBMIT))
async def withdraw(review_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    await service.withdraw(db, review, user["id"])
    return await service.detail(db, review, user, held)


@review_router.post(
    "/{review_id}/documents/{document_id}/decision",
    response_model=PlanReviewDetail,
    summary="Approve, Approve with Comments, or Reject a Document",
    description="Client-team members only. A comment is required unless approving outright. When every document "
    "is decided the review is `reviewed`, with the worst decision as its outcome.",
    dependencies=perm(P.REVIEW),
)
async def decide(
    review_id: Id,
    document_id: Id,
    values: DocumentDecision,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    await service.decide(db, review, document_id, values.decision, values.comment, user["id"])
    return await service.detail(db, review, user, held)


@review_router.post(
    "/{review_id}/comments",
    response_model=PlanReviewDetail,
    summary="Comment on the Package or a Document",
    description="Clients need `portal.review`, staff `portal.submit`. The other side is notified.",
    dependencies=perm(P.READ),
)
async def comment(
    review_id: Id, values: ReviewCommentCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    review = await service.visible_review(db, review_id, user, held)
    if not (user.get("is_superuser") or P.REVIEW.value in held or P.SUBMIT.value in held):
        raise service.NotReviewer(str(review_id))
    await service.add_comment(db, review, values.body, values.document_id, user, held)
    return await service.detail(db, review, user, held)


@review_router.get(
    "/{review_id}/documents/{document_id}/download",
    summary="Download a Shared Document",
    description="For the client: their review's documents, without access to the project's file store.",
    dependencies=perm(P.READ),
)
async def download(
    review_id: Id,
    document_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    inline: bool = False,
) -> FileResponse:
    review = await service.visible_review(db, review_id, user, held)
    f = await service.document_file(db, review, document_id)
    show = inline and f.content_type in {"application/pdf", "image/png", "image/jpeg"}
    return FileResponse(
        storage().path(f.storage_key),
        media_type=f.content_type if show else "application/octet-stream",
        headers={
            "Content-Disposition": f"{'inline' if show else 'attachment'}; filename*=UTF-8''{quote(f.name)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
