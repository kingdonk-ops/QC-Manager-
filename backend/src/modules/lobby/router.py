"""Mounted at /api/v1/lobby."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..projects.models import Project
from ..projects.permissions import ProjectPermissionName
from ..projects.service import readable_project, visible_project_ids
from . import service
from .constants import InviteStatus
from .models import AccessRequest, ProjectInvite
from .schemas import (
    AccessRequestCreate,
    AccessRequestRead,
    ApproveRequest,
    InviteCreate,
    InviteCreated,
    InvitePreview,
    InviteRead,
    InviteToken,
    Joined,
    ListingRead,
    ListingSet,
    LobbyProject,
    MemberRead,
    ProjectRef,
    RejectRequest,
)

router = APIRouter(tags=["Project Lobby"])

Id = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
MANAGE = [require_permissions(ProjectPermissionName.MANAGE_ACCESS.value)]

NO_STORE = {"Cache-Control": "no-store"}


def _joined(project: Project) -> Joined:
    return Joined(project_id=project.id, project_code=project.code, project_name=project.name)


# --- the lobby ----------------------------------------------------------------------------------


@router.get(
    "/projects/",
    response_model=PaginatedListResponse[LobbyProject],
    summary="Projects You Can Ask to Join",
    description="Internal staff: projects listed in the lobby that you can't see yet. Everyone: projects you hold a "
    "pending invite for. Each carries your latest request's status.",
)
async def lobby_projects(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
) -> Any:
    rows = await service.lobby_projects(db, user, held)
    start = compute_offset(page, items_per_page)
    data = {"data": rows[start : start + items_per_page], "total_count": len(rows)}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get(
    "/lookup",
    response_model=ProjectRef,
    summary="Find a Project by Its Exact Code",
    description="Internal staff only. Finding a project grants nothing: file an access request next.",
)
async def lookup(db: AsyncSessionDep, user: CurrentUserDep, code: Annotated[str, Query(min_length=1, max_length=30)]) -> Any:
    project = await service.lookup(db, user, code)
    return ProjectRef(id=project.id, code=project.code, name=project.name)


@router.post(
    "/claim",
    response_model=list[Joined],
    summary="Join the Projects Your Invites Created Your Account For",
    description="Called once signed in: an account created by a project invite joins those projects at its first sign-in.",
)
async def claim(db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    return [_joined(p) for p in await service.claim_invites(db, user)]


# --- access requests ----------------------------------------------------------------------------


@router.get(
    "/requests/mine",
    response_model=list[AccessRequestRead],
    summary="Your Active Requests",
    description="Pending requests, and the latest decision per project from the last 30 days, with when a rejected "
    "request may be made again.",
)
async def my_requests(db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    return await service.read_requests(db, await service.my_requests(db, user["id"]))


@router.post(
    "/requests",
    response_model=AccessRequestRead,
    status_code=201,
    summary="Request Access to a Project",
    description="Internal staff, for a project listed in the lobby or named by its exact `code`. 409 while a request "
    "is pending, when you already have access, or within the cooldown after a rejection.",
)
async def file_request(
    values: AccessRequestCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    if values.project_id is None and not values.code:
        raise UnprocessableEntityException("Name the project by id or code.")
    r = await service.file_request(db, user, held, values.project_id, values.code, values.message)
    return (await service.read_requests(db, [r]))[0]


@router.post("/requests/{request_id}/withdraw", response_model=AccessRequestRead, summary="Withdraw Your Request")
async def withdraw(request_id: Id, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    r = await service.get_request(db, request_id)
    await service.withdraw(db, r, user)
    return (await service.read_requests(db, [r]))[0]


@router.get(
    "/requests/",
    response_model=PaginatedListResponse[AccessRequestRead],
    summary="Access Requests to Decide",
    description="Requests for the projects you can read and manage access to; pending by default.",
    dependencies=MANAGE,
)
async def requests_to_decide(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    project_id: Annotated[int | None, Query(ge=1, le=MAX_INTEGER_ID)] = None,
    status: Literal["pending", "approved", "rejected", "withdrawn", "all"] = "pending",
) -> Any:
    visible = await visible_project_ids(db, user["id"], held)
    if project_id is not None:
        await readable_project(db, project_id, user["id"], held)
        visible &= {project_id}
    where: list[Any] = [AccessRequest.project_id.in_(visible)]
    if status != "all":
        where.append(AccessRequest.status == status)
    total = await db.scalar(select(func.count()).select_from(AccessRequest).where(*where))
    rows = (
        await db.execute(
            select(AccessRequest)
            .where(*where)
            .order_by(AccessRequest.id.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": await service.read_requests(db, list(rows)), "total_count": total or 0}
    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.post(
    "/requests/{request_id}/approve",
    response_model=AccessRequestRead,
    summary="Approve an Access Request",
    description="`member` writes a direct project member; `client_team` adds them to the project's client team. "
    "Never your own request.",
    dependencies=MANAGE,
)
async def approve(
    request_id: Id, values: ApproveRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await service.get_request(db, request_id)
    await service.approve(db, r, values.grant.value if values.grant else None, user, held)
    return (await service.read_requests(db, [r]))[0]


@router.post(
    "/requests/{request_id}/reject",
    response_model=AccessRequestRead,
    summary="Reject an Access Request",
    description="The optional reason (up to 500 characters) is shown to the requester.",
    dependencies=MANAGE,
)
async def reject(
    request_id: Id, values: RejectRequest, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    r = await service.get_request(db, request_id)
    await service.reject(db, r, values.reason, user, held)
    return (await service.read_requests(db, [r]))[0]


# --- project access settings --------------------------------------------------------------------


@router.get("/projects/{project_id}/listing", response_model=ListingRead, summary="Is the Project Listed in the Lobby")
async def get_listing(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    await readable_project(db, project_id, user["id"], held)
    return ListingRead(project_id=project_id, visible=await service.is_listed(db, project_id))


@router.put(
    "/projects/{project_id}/listing",
    response_model=ListingRead,
    summary="List or Unlist the Project in the Lobby",
    dependencies=MANAGE,
)
async def set_listing(
    project_id: Id, values: ListingSet, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    await service.can_manage(db, project_id, user, held)
    await service.set_listing(db, project_id, values.visible, user["id"])
    return ListingRead(project_id=project_id, visible=values.visible)


@router.get(
    "/projects/{project_id}/members",
    response_model=list[MemberRead],
    summary="Who Was Given Access",
    description="Direct project members and the project's client team.",
    dependencies=MANAGE,
)
async def members(project_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    project = await service.can_manage(db, project_id, user, held)
    return await service.members(db, project)


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    summary="Remove a Direct Member",
    dependencies=MANAGE,
)
async def remove_member(
    project_id: Id, user_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> dict[str, str]:
    await service.can_manage(db, project_id, user, held)
    await service.remove_member(db, project_id, user_id)
    return {"message": "Member removed"}


# --- invites ------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/invites",
    response_model=list[InviteRead],
    summary="The Project's Invites",
    dependencies=MANAGE,
)
async def invites(
    project_id: Id,
    db: AsyncSessionDep,
    user: CurrentUserDep,
    held: CurrentPermissionsDep,
    status: Literal["pending", "accepted", "revoked", "all"] = "pending",
) -> Any:
    await service.can_manage(db, project_id, user, held)
    where: list[Any] = [ProjectInvite.project_id == project_id]
    if status != "all":
        where.append(ProjectInvite.status == status)
    rows = (await db.execute(select(ProjectInvite).where(*where).order_by(ProjectInvite.id.desc()))).scalars()
    return await service.read_invites(db, list(rows))


@router.post(
    "/projects/{project_id}/invites",
    response_model=InviteCreated,
    status_code=201,
    summary="Invite Someone to the Project",
    description="Emails a single-use link bound to the address, valid for 7 days; the link is also returned once. "
    "Someone without an account gets an external account and a set-password email, and joins at first sign-in. "
    "A new invite to the same address revokes the earlier one.",
    dependencies=MANAGE,
)
async def invite(
    project_id: Id, values: InviteCreate, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep
) -> Any:
    project = await service.can_manage(db, project_id, user, held)
    created, token = await service.create_invite(db, project, values.model_dump(), user)
    return {**(await service.read_invites(db, [created]))[0], "link": service.invite_link(token)}


async def _managed_invite(db: Any, invite_id: int, user: dict[str, Any], held: frozenset[str]) -> tuple[ProjectInvite, Project]:
    invite = await service.get_invite(db, invite_id)
    project = await service.can_manage(db, invite.project_id, user, held)
    return invite, project


@router.post("/invites/{invite_id}/revoke", response_model=InviteRead, summary="Revoke an Invite", dependencies=MANAGE)
async def revoke(invite_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    invite, _ = await _managed_invite(db, invite_id, user, held)
    await service.revoke(db, invite)
    return (await service.read_invites(db, [invite]))[0]


@router.post(
    "/invites/{invite_id}/resend",
    response_model=InviteCreated,
    summary="Re-send an Invite",
    description="A new link and expiry; the old link stops working.",
    dependencies=MANAGE,
)
async def resend(invite_id: Id, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep) -> Any:
    invite, project = await _managed_invite(db, invite_id, user, held)
    token = await service.resend(db, invite, project, user)
    return {**(await service.read_invites(db, [invite]))[0], "link": service.invite_link(token)}


@router.post(
    "/invites/preview",
    response_model=InvitePreview,
    summary="What an Invite Link Is For",
    description="The token travels in the body, never the URL. 410 for a link that was used, revoked, replaced or has expired.",
)
async def preview(values: InviteToken, response: Response, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    response.headers.update(NO_STORE)
    invite = await service.by_token(db, values.token)
    if invite.status != InviteStatus.PENDING or service.expired(invite):
        raise service.Gone()
    project = await db.get(Project, invite.project_id)
    if project is None:
        raise service.Gone()
    return InvitePreview(
        project_id=project.id,
        project_code=project.code,
        project_name=project.name,
        email_hint=service.email_hint(invite.email),
        for_you=invite.email.lower() == str(user["email"]).lower(),
        status=invite.status,
        expires_at=invite.expires_at,
    )


@router.post(
    "/invites/accept",
    response_model=Joined,
    summary="Join the Project an Invite Link Is For",
    description="Single use, before it expires, and only from the invited email's account (403 otherwise).",
)
async def accept(values: InviteToken, response: Response, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    response.headers.update(NO_STORE)
    return _joined(await service.accept(db, values.token, user))


@router.post(
    "/invites/{invite_id}/join",
    response_model=Joined,
    summary="Join from the Lobby",
    description="Accept a pending invite addressed to your account's email, as listed in the lobby.",
)
async def join(invite_id: Id, db: AsyncSessionDep, user: CurrentUserDep) -> Any:
    return _joined(await service.join(db, invite_id, user))
