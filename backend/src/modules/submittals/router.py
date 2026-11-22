"""Mounted at /api/v1/submittals."""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, or_, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import history_of
from ...infrastructure.tabular import write_table
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.service import readable_project
from . import service
from .constants import OPEN_STATUSES, ReviewState, SubmittalStatus, SubmittalType
from .models import Submittal, SubmittalReview
from .permissions import SubmittalPermissionName as P
from .schemas import (
    SubmittalCreate,
    SubmittalDetail,
    SubmittalHistoryRead,
    SubmittalNote,
    SubmittalRead,
    SubmittalReviewDecision,
    SubmittalReviewerOption,
    SubmittalRevise,
    SubmittalRevisionRead,
    SubmittalUpdate,
)

router = APIRouter(tags=["Submittals"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


def perm(name: P) -> list[Any]:
    return [require_permissions(name.value)]


def _filters(
    project_id: int,
    user_id: int,
    status: SubmittalStatus | None,
    reviewer: str | None,
    spec_section: str | None,
    overdue: bool,
    type: SubmittalType | None,
    search: str | None,
) -> list[Any]:
    where: list[Any] = [Submittal.project_id == project_id]
    if status:
        where.append(Submittal.status == status.value)
    if reviewer:
        uid = user_id if reviewer == "me" else int(reviewer)
        where.append(
            Submittal.id.in_(
                select(SubmittalReview.submittal_id).where(
                    SubmittalReview.reviewer_id == uid, SubmittalReview.state == ReviewState.OPEN.value
                )
            )
        )
    if spec_section:
        where.append(func.lower(Submittal.spec_section).like(f"{spec_section.lower()}%"))
    if overdue:
        where += [Submittal.required_by < date.today(), Submittal.status.in_(OPEN_STATUSES)]
    if type:
        where.append(Submittal.type == type.value)
    if search:
        like = f"%{search.lower()}%"
        where.append(or_(func.lower(Submittal.title).like(like), func.lower(Submittal.code).like(like)))
    return where


Reviewer = Annotated[str | None, Query(pattern=r"^(me|\d{1,10})$", description="`me`, or a user id: open reviews only")]
SpecSection = Annotated[str | None, Query(max_length=50)]
Search = Annotated[str | None, Query(max_length=100)]


@router.get(
    "/",
    response_model=PaginatedListResponse[SubmittalRead],
    summary="The Submittal Register",
    description="With current reviewers and days outstanding. Filter by status, reviewer (`me`), spec section, "
    "overdue, type or text.",
    dependencies=perm(P.READ),
)
async def list_submittals(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    status: SubmittalStatus | None = None,
    reviewer: Reviewer = None,
    spec_section: SpecSection = None,
    overdue: bool = False,
    type: SubmittalType | None = None,
    search: Search = None,
) -> Any:
    await readable_project(db, project_id, user["id"], held)
    where = _filters(project_id, user["id"], status, reviewer, spec_section, overdue, type, search)
    total = await db.scalar(select(func.count()).select_from(Submittal).where(*where))
    rows = (
        await db.execute(
            select(Submittal)
            .where(*where)
            .order_by(Submittal.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_many(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post("/", response_model=SubmittalDetail, status_code=201, summary="Create a Submittal", dependencies=perm(P.CREATE))
async def create(values: SubmittalCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, values.project_id, user["id"], held)
    s = await service.create(db, values.model_dump(), user)
    return await service.detail(db, s, user)


@router.get(
    "/reviewers/",
    response_model=PaginatedListResponse[SubmittalReviewerOption],
    summary="People Who Can Review Submittals",
    dependencies=perm(P.READ),
)
async def reviewers(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    search: Search = None,
) -> Any:
    data = await service.reviewer_options(db, search, compute_offset(page, items_per_page), items_per_page)
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get(
    "/export",
    summary="Export the Register",
    description="The filtered register as Excel, CSV or PDF.",
    response_class=Response,
    dependencies=perm(P.EXPORT),
)
async def export(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    project_id: Annotated[int, Query(ge=1, le=MAX_INTEGER_ID)],
    format: Literal["xlsx", "csv", "pdf"] = "xlsx",
    status: SubmittalStatus | None = None,
    reviewer: Reviewer = None,
    spec_section: SpecSection = None,
    overdue: bool = False,
    type: SubmittalType | None = None,
    search: Search = None,
) -> Response:
    project = await readable_project(db, project_id, user["id"], held)
    where = _filters(project_id, user["id"], status, reviewer, spec_section, overdue, type, search)
    rows = list((await db.execute(select(Submittal).where(*where).order_by(Submittal.id).limit(5000))).scalars())
    read = await service.read_many(db, rows)
    for r in read:
        r["rev"] = f"Rev {r['revision_letter']}"
        r["reviewers"] = ", ".join(r["current_reviewers"])
        r["type_label"] = r["type"].replace("_", " ")
        r["status_label"] = r["status"].replace("_", " ")
    columns = [
        ("code", "Code"),
        ("title", "Title"),
        ("type_label", "Type"),
        ("spec_section", "Spec section"),
        ("rev", "Revision"),
        ("status_label", "Status"),
        ("submitted_by_name", "Submitted by"),
        ("reviewers", "Current reviewers"),
        ("required_by", "Required by"),
        ("days_outstanding", "Days outstanding"),
    ]
    stem = f"submittals-{project.code}"
    if format == "pdf":
        doc = Document(title="Submittal register", subtitle=f"{project.code} · {project.name}", landscape=True)
        doc.table(
            [h for _, h in columns],
            [[r.get(k) if r.get(k) is not None else "" for k, _ in columns] for r in read],
            widths=[0.07, 0.22, 0.1, 0.08, 0.06, 0.1, 0.12, 0.13, 0.07, 0.05],
            numeric={9},
        )
        return Response(
            render_pdf(doc),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'},
        )
    body, media_type, ext = write_table(columns, read, format, title="Submittals")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{stem}.{ext}"'})


async def _readable(db: AsyncSessionDep, submittal_id: int, user: dict[str, Any], held: frozenset[str]) -> Submittal:
    s = await service.get_submittal(db, submittal_id)
    await readable_project(db, s.project_id, user["id"], held)
    return s


@router.get("/{submittal_id}", response_model=SubmittalDetail, summary="Get a Submittal", dependencies=perm(P.READ))
async def get(submittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.detail(db, await _readable(db, submittal_id, user, held), user)


@router.patch("/{submittal_id}", response_model=SubmittalDetail, summary="Update a Submittal", dependencies=perm(P.UPDATE))
async def update(
    submittal_id: Id, values: SubmittalUpdate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, submittal_id, user, held)
    await service.update(db, s, values.model_dump(exclude_unset=True))
    return await service.detail(db, s, user)


@router.delete("/{submittal_id}", summary="Delete a Submittal", dependencies=perm(P.DELETE))
async def delete(submittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> dict[str, str]:
    s = await _readable(db, submittal_id, user, held)
    await db.delete(s)
    await db.commit()
    return {"message": "Submittal deleted"}


@router.post(
    "/{submittal_id}/submit",
    response_model=SubmittalDetail,
    summary="Submit for Review",
    description="Opens the first step of the workflow and notifies its reviewers.",
    dependencies=perm(P.SUBMIT),
)
async def submit(
    submittal_id: Id, values: SubmittalNote, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, submittal_id, user, held)
    await service.submit(db, s, user, values.note)
    return await service.detail(db, s, user)


@router.post(
    "/{submittal_id}/review",
    response_model=SubmittalDetail,
    summary="Decide Your Open Review Step",
    description="Approved / approved as noted move the review on when the step is complete; revise and resubmit or "
    "rejected end it at once. The outcome is the most severe decision of the final step.",
    dependencies=perm(P.REVIEW),
)
async def review(
    submittal_id: Id, values: SubmittalReviewDecision, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, submittal_id, user, held)
    await service.review(db, s, user, values.decision.value, values.comment)
    return await service.detail(db, s, user)


@router.post(
    "/{submittal_id}/revise",
    response_model=SubmittalDetail,
    summary="Start the Next Revision",
    description="Rev B, Rev C, ... with the given files, a fresh workflow cycle, and the earlier cycles kept.",
    dependencies=perm(P.SUBMIT),
)
async def revise(
    submittal_id: Id, values: SubmittalRevise, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, submittal_id, user, held)
    await service.revise(
        db,
        s,
        user,
        held,
        note=values.note,
        file_ids=values.file_ids,
        workflow=[step.model_dump() for step in values.workflow] if values.workflow is not None else None,
        submit_now=values.submit,
    )
    return await service.detail(db, s, user)


@router.post("/{submittal_id}/close", response_model=SubmittalDetail, summary="Close a Submittal", dependencies=perm(P.UPDATE))
async def close(
    submittal_id: Id, values: SubmittalNote, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    s = await _readable(db, submittal_id, user, held)
    await service.close(db, s, user, values.note)
    return await service.detail(db, s, user)


@router.get(
    "/{submittal_id}/revisions",
    response_model=list[SubmittalRevisionRead],
    summary="Every Review Cycle",
    description="Newest first, each with its decisions and files, for comparison.",
    dependencies=perm(P.READ),
)
async def revisions(submittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    return await service.revisions(db, await _readable(db, submittal_id, user, held))


@router.get(
    "/{submittal_id}/history", response_model=list[SubmittalHistoryRead], summary="Status History", dependencies=perm(P.READ)
)
async def history(submittal_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    s = await _readable(db, submittal_id, user, held)
    rows = await history_of(db, service.ENTITY, s.id)
    names = await service.user_names(db, {r["changed_by_id"] for r in rows if r["changed_by_id"]})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"])} for r in rows]
