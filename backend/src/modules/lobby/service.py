"""Access requests, project invites and the lobby listing.

* **Lobby**: internal staff (Entra-linked accounts and superusers) see the projects a project admin listed in
  the lobby, or find one by its exact code, and file an access request. External people see only the projects
  they hold a pending invite for.
* **Access requests**: ``pending -> approved | rejected`` by a holder of ``projects.manage_access`` who can read
  the project (never the requester), ``pending -> withdrawn`` by the requester. One pending request per user and
  project. After a rejection a new request waits ``ACCESS_REQUEST_COOLDOWN_HOURS`` (409 with the time until then);
  a withdrawal has no cooldown.
* **Invites**: a random token (only its SHA-256 is stored), single-use, expiring after ``INVITE_TTL_HOURS``, bound
  to the invited email: accepting from another account is refused. A re-invite or a resend revokes the earlier
  token. Someone without an account gets an external account (the portal's invitation flow: a set-password
  email) and joins the project at their first sign-in (``claim_invites``).
* **Granting** (``grant_access``): ``client_team`` adds the person to the project's client team; ``member``
  writes a direct ``ProjectMember`` row. Either makes ``readable_project`` let them in.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import settings
from ...infrastructure.http_exceptions import ConflictException, CustomException, ForbiddenException, NotFoundException
from ...infrastructure.mail import Mail, deliver
from ..notifications.constants import Category
from ..notifications.service import notify
from ..portal.service import new_external_account, send_set_password_link
from ..projects.models import Project, ProjectMember
from ..projects.permissions import ProjectPermissionName
from ..projects.service import add_member, readable_project, visible_project_ids
from ..role.models import RolePermission, UserRole
from ..team.models import Team, TeamMembership
from ..user.models import User
from . import constants
from .constants import PANEL_WINDOW, Grant, InviteStatus, RequestStatus
from .models import AccessRequest, LobbyListing, ProjectInvite


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_internal(user: dict[str, Any]) -> bool:
    """Company staff: signed in with Entra (or a superuser). Everyone else is external."""
    return bool(user.get("entra_id")) or bool(user.get("is_superuser"))


def cooldown() -> timedelta:
    return timedelta(hours=constants.ACCESS_REQUEST_COOLDOWN_HOURS)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Gone(CustomException):
    def __init__(self, detail: str = "This invite link is no longer valid.") -> None:
        super().__init__(status_code=410, detail=detail)


async def managers(db: AsyncSession, project_id: int) -> list[int]:
    """Holders of ``projects.manage_access`` (through a role) who can read the project, and superusers."""
    holders = set(
        (
            await db.execute(
                select(UserRole.user_id)
                .join(RolePermission, RolePermission.role_id == UserRole.role_id)
                .where(RolePermission.permission_name == ProjectPermissionName.MANAGE_ACCESS.value)
            )
        ).scalars()
    )
    supers = set((await db.execute(select(User.id).where(User.is_superuser.is_(True), User.is_deleted.is_(False)))).scalars())
    out = set(supers)
    for uid in holders - supers:
        held = set(
            (
                await db.execute(
                    select(RolePermission.permission_name)
                    .join(UserRole, UserRole.role_id == RolePermission.role_id)
                    .where(UserRole.user_id == uid)
                )
            ).scalars()
        )
        if project_id in await visible_project_ids(db, uid, frozenset(held)):
            out.add(uid)
    return sorted(out)


async def can_manage(db: AsyncSession, project_id: int, user: dict[str, Any], held: frozenset[str]) -> Project:
    """The project, when the caller may manage access to it; 404 when they can't read it, 403 when they can't manage."""
    project = await readable_project(db, project_id, user["id"], held)
    if not (user.get("is_superuser") or ProjectPermissionName.MANAGE_ACCESS.value in held):
        raise ForbiddenException("You can't manage access to this project.")
    return project


# --- granting -----------------------------------------------------------------------------------


async def grant_access(db: AsyncSession, project: Project, user_id: int, grant: str, source: str, by: int | None) -> str:
    """Let the user read the project (no commit). Returns the grant actually used."""
    if grant == Grant.CLIENT_TEAM and project.client_team_id is not None:
        team = await db.get(Team, project.client_team_id)
        if team is not None and not team.entra_group_id:
            if await db.get(TeamMembership, (team.id, user_id)) is None:
                db.add(TeamMembership(team_id=team.id, user_id=user_id))
                await db.flush()
            return Grant.CLIENT_TEAM.value
    await add_member(db, project.id, user_id, source, by)
    return Grant.MEMBER.value


def default_grant(project: Project, external: bool) -> str:
    return Grant.CLIENT_TEAM.value if external and project.client_team_id else Grant.MEMBER.value


# --- lobby --------------------------------------------------------------------------------------


async def latest_requests(db: AsyncSession, user_id: int) -> dict[int, AccessRequest]:
    rows = (
        await db.execute(select(AccessRequest).where(AccessRequest.user_id == user_id).order_by(AccessRequest.id))
    ).scalars()
    return {r.project_id: r for r in rows}


async def pending_invites_for(db: AsyncSession, email: str) -> list[ProjectInvite]:
    rows = await db.execute(
        select(ProjectInvite).where(
            func.lower(ProjectInvite.email) == email.lower(),
            ProjectInvite.status == InviteStatus.PENDING.value,
            ProjectInvite.expires_at > utcnow(),
        )
    )
    return list(rows.scalars())


async def lobby_projects(db: AsyncSession, user: dict[str, Any], held: frozenset[str]) -> list[dict[str, Any]]:
    """What the caller can ask to join: listed projects (internal staff) and projects they're invited to."""
    readable = await visible_project_ids(db, user["id"], held)
    invites = {i.project_id: i for i in await pending_invites_for(db, user["email"])}
    ids = set(invites)
    if is_internal(user):
        ids |= set((await db.execute(select(LobbyListing.project_id).where(LobbyListing.visible.is_(True)))).scalars())
    ids -= readable
    if not ids:
        return []
    projects = (await db.execute(select(Project).where(Project.id.in_(ids)).order_by(Project.code))).scalars()
    latest = await latest_requests(db, user["id"])
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "client_name": p.client_name,
            "request_status": latest[p.id].status if p.id in latest else None,
            "invite_id": invites[p.id].id if p.id in invites else None,
            "invite_expires_at": invites[p.id].expires_at if p.id in invites else None,
        }
        for p in projects
    ]


async def lookup(db: AsyncSession, user: dict[str, Any], code: str) -> Project:
    if not is_internal(user):
        raise NotFoundException("No project with that code.")
    project = await db.scalar(select(Project).where(func.lower(Project.code) == code.strip().lower()))
    if project is None:
        raise NotFoundException("No project with that code.")
    return project


async def set_listing(db: AsyncSession, project_id: int, visible: bool, user_id: int) -> None:
    row = await db.get(LobbyListing, project_id)
    if row is None:
        db.add(LobbyListing(project_id=project_id, visible=visible, updated_by_id=user_id))
    else:
        row.visible, row.updated_by_id = visible, user_id
    await db.commit()


async def is_listed(db: AsyncSession, project_id: int) -> bool:
    row = await db.get(LobbyListing, project_id)
    return bool(row and row.visible)


# --- access requests ----------------------------------------------------------------------------


def request_again_at(r: AccessRequest) -> datetime | None:
    if r.status != RequestStatus.REJECTED or r.decided_at is None:
        return None
    return _aware(r.decided_at) + cooldown()


async def read_requests(db: AsyncSession, rows: list[AccessRequest]) -> list[dict[str, Any]]:
    projects = {
        p.id: p for p in (await db.execute(select(Project).where(Project.id.in_({r.project_id for r in rows})))).scalars()
    }
    people = {r.user_id for r in rows} | {r.decided_by_id for r in rows if r.decided_by_id}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(people)))).scalars()} if people else {}
    out = []
    for r in rows:
        p = projects.get(r.project_id)
        requester = users.get(r.user_id)
        decider = users.get(r.decided_by_id) if r.decided_by_id else None
        out.append(
            {
                "id": r.id,
                "project_id": r.project_id,
                "project_code": p.code if p else "",
                "project_name": p.name if p else "",
                "user_id": r.user_id,
                "user_name": requester.name if requester else None,
                "user_email": requester.email if requester else None,
                "message": r.message,
                "status": r.status,
                "grant": r.grant,
                "rejection_reason": r.rejection_reason,
                "decided_by_name": decider.name if decider else None,
                "decided_at": r.decided_at,
                "withdrawn_at": r.withdrawn_at,
                "created_at": r.created_at,
                "request_again_at": request_again_at(r),
            }
        )
    return out


async def file_request(
    db: AsyncSession, user: dict[str, Any], held: frozenset[str], project_id: int | None, code: str | None, message: str | None
) -> AccessRequest:
    """File a request. 404 unless the project is listed or named by its exact code (or asked for before)."""
    if not is_internal(user):
        raise NotFoundException("Ask the project team for an invite.")
    project: Project | None = None
    if code:
        project = await lookup(db, user, code)
    elif project_id is not None:
        project = await db.get(Project, project_id)
        asked_before = await db.scalar(
            select(AccessRequest.id).where(AccessRequest.user_id == user["id"], AccessRequest.project_id == project_id).limit(1)
        )
        if project is not None and not (asked_before or await is_listed(db, project.id)):
            project = None
    if project is None:
        raise NotFoundException("Project not found.")
    if project.id in await visible_project_ids(db, user["id"], held):
        raise ConflictException("You already have access to this project.")
    previous = list(
        (
            await db.execute(
                select(AccessRequest)
                .where(AccessRequest.user_id == user["id"], AccessRequest.project_id == project.id)
                .order_by(AccessRequest.id.desc())
            )
        ).scalars()
    )
    if any(r.status == RequestStatus.PENDING for r in previous):
        raise ConflictException("You already have a pending request for this project.")
    last_rejected = next((r for r in previous if r.status == RequestStatus.REJECTED), None)
    if last_rejected is not None and previous[0].status == RequestStatus.REJECTED:
        allowed = request_again_at(last_rejected)
        if allowed is not None and utcnow() < allowed:
            raise ConflictException(f"You can request access again from {allowed.isoformat(timespec='minutes')}.")
    request = AccessRequest(user_id=user["id"], project_id=project.id, message=message)
    db.add(request)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException("You already have a pending request for this project.") from exc
    await notify(
        db,
        await managers(db, project.id),
        Category.APPROVAL,
        f"{user['name']} asks to join {project.code}",
        body=message,
        link=f"/lobby/requests?project={project.id}",
        entity=("access_request", request.id),
        actor_id=user["id"],
    )
    await db.commit()
    return request


async def get_request(db: AsyncSession, request_id: int) -> AccessRequest:
    r = await db.get(AccessRequest, request_id)
    if r is None:
        raise NotFoundException("Request not found.")
    return r


async def withdraw(db: AsyncSession, r: AccessRequest, user: dict[str, Any]) -> None:
    if r.user_id != user["id"]:
        raise NotFoundException("Request not found.")
    if r.status != RequestStatus.PENDING:
        raise ConflictException("Only a pending request can be withdrawn.")
    r.status, r.withdrawn_at = RequestStatus.WITHDRAWN.value, utcnow()
    await db.commit()


async def _decidable(db: AsyncSession, r: AccessRequest, user: dict[str, Any], held: frozenset[str]) -> Project:
    project = await can_manage(db, r.project_id, user, held)
    if r.user_id == user["id"]:
        raise ForbiddenException("You can't decide your own request.")
    if r.status != RequestStatus.PENDING:
        raise ConflictException("This request has already been decided or withdrawn.")
    return project


async def approve(db: AsyncSession, r: AccessRequest, grant: str | None, user: dict[str, Any], held: frozenset[str]) -> None:
    project = await _decidable(db, r, user, held)
    requester = await db.get(User, r.user_id)
    external = requester is not None and not (requester.entra_id or requester.is_superuser)
    used = await grant_access(db, project, r.user_id, grant or default_grant(project, external), "access_request", user["id"])
    r.status, r.grant, r.decided_by_id, r.decided_at = RequestStatus.APPROVED.value, used, user["id"], utcnow()
    await notify(
        db,
        [r.user_id],
        Category.APPROVAL,
        f"You've been given access to {project.code} {project.name}",
        link=f"/?project={project.id}",
        entity=("access_request", r.id),
        actor_id=user["id"],
    )
    await db.commit()


async def reject(db: AsyncSession, r: AccessRequest, reason: str | None, user: dict[str, Any], held: frozenset[str]) -> None:
    project = await _decidable(db, r, user, held)
    r.status, r.rejection_reason = RequestStatus.REJECTED.value, reason
    r.decided_by_id, r.decided_at = user["id"], utcnow()
    await notify(
        db,
        [r.user_id],
        Category.APPROVAL,
        f"Your request to join {project.code} was declined",
        body=reason,
        link="/lobby",
        entity=("access_request", r.id),
        actor_id=user["id"],
    )
    await db.commit()


# --- members ------------------------------------------------------------------------------------


async def members(db: AsyncSession, project: Project) -> list[dict[str, Any]]:
    out = []
    direct = await db.execute(
        select(ProjectMember, User).join(User, User.id == ProjectMember.user_id).where(ProjectMember.project_id == project.id)
    )
    for m, u in direct.all():
        out.append(_member(u, m.source, "direct", m.created_at))
    if project.client_team_id:
        team = await db.execute(
            select(TeamMembership, User)
            .join(User, User.id == TeamMembership.user_id)
            .where(TeamMembership.team_id == project.client_team_id)
        )
        for tm, u in team.all():
            out.append(_member(u, "team", "client_team", tm.created_at))
    return sorted(out, key=lambda m: m["name"].lower())


def _member(u: User, source: str, via: str, at: datetime | None) -> dict[str, Any]:
    return {
        "user_id": u.id,
        "name": u.name,
        "email": u.email,
        "account_type": "staff" if u.entra_id or u.is_superuser else "external",
        "source": source,
        "via": via,
        "added_at": at,
    }


async def remove_member(db: AsyncSession, project_id: int, user_id: int) -> None:
    row = await db.get(ProjectMember, (project_id, user_id))
    if row is None:
        raise NotFoundException("Not a direct member of this project.")
    await db.delete(row)
    await db.commit()


# --- invites ------------------------------------------------------------------------------------


def invite_link(token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/invite#{token}"


def expired(invite: ProjectInvite, at: datetime | None = None) -> bool:
    return _aware(invite.expires_at) <= (at or utcnow())


async def read_invites(db: AsyncSession, rows: list[ProjectInvite]) -> list[dict[str, Any]]:
    ids = {i.invited_by_id for i in rows if i.invited_by_id}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all()) if ids else {}
    now = utcnow()
    return [
        {
            "id": i.id,
            "project_id": i.project_id,
            "email": i.email,
            "grant": i.grant,
            "status": i.status,
            "expired": i.status == InviteStatus.PENDING and expired(i, now),
            "expires_at": i.expires_at,
            "created_account": i.created_account,
            "invited_by_name": names.get(i.invited_by_id) if i.invited_by_id else None,
            "last_sent_at": i.last_sent_at,
            "accepted_at": i.accepted_at,
            "created_at": i.created_at,
        }
        for i in rows
    ]


async def _send_invite(db: AsyncSession, invite: ProjectInvite, project: Project, token: str, inviter: str) -> None:
    lines = [f"{inviter} has invited you to the project {project.code} {project.name}."]
    if invite.message:
        lines += ["", invite.message]
    if invite.created_account:
        lines += [
            "",
            "We've also sent you a separate email to set your password. Once you've set it and signed in, "
            "you're in the project.",
        ]
    lines += [
        "",
        f"Join the project: {invite_link(token)}",
        "",
        f"The link works once, until {invite.expires_at:%d %b %Y %H:%M} UTC.",
    ]
    await deliver(Mail(to=[invite.email], subject=f"Invitation to {project.code} {project.name}", text="\n".join(lines)))
    invite.last_sent_at = utcnow()


async def _revoke_pending(db: AsyncSession, project_id: int, email: str) -> None:
    await db.execute(
        update(ProjectInvite)
        .where(
            ProjectInvite.project_id == project_id,
            func.lower(ProjectInvite.email) == email,
            ProjectInvite.status == InviteStatus.PENDING.value,
        )
        .values(status=InviteStatus.REVOKED.value, revoked_at=utcnow())
    )


async def create_invite(
    db: AsyncSession, project: Project, values: dict[str, Any], inviter: dict[str, Any]
) -> tuple[ProjectInvite, str]:
    email = str(values["email"]).lower()
    account = await db.scalar(select(User).where(func.lower(User.email) == email, User.is_deleted.is_(False)))
    created = False
    if account is None:
        account = await new_external_account(db, values.get("name") or email.split("@", 1)[0], email)
        created = True
    external = not (account.entra_id or account.is_superuser)
    if account.id in await visible_project_ids(db, account.id, frozenset()):
        raise ConflictException("They already have access to this project.")
    await _revoke_pending(db, project.id, email)
    token = secrets.token_urlsafe(32)
    grant = values.get("grant")
    invite = ProjectInvite(
        project_id=project.id,
        email=email,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(hours=constants.INVITE_TTL_HOURS),
        grant=str(grant.value if hasattr(grant, "value") else grant) if grant else default_grant(project, external),
        user_id=account.id,
        created_account=created,
        message=values.get("message"),
        invited_by_id=inviter["id"],
    )
    db.add(invite)
    await db.flush()
    await _send_invite(db, invite, project, token, inviter["name"])
    await notify(
        db,
        [account.id],
        Category.SYSTEM,
        f"You're invited to {project.code} {project.name}",
        link="/lobby",
        entity=("project_invite", invite.id),
        actor_id=inviter["id"],
    )
    await db.commit()
    if created:
        await send_set_password_link(db, email, redirect_to="/lobby")
    return invite, token


async def get_invite(db: AsyncSession, invite_id: int) -> ProjectInvite:
    invite = await db.get(ProjectInvite, invite_id)
    if invite is None:
        raise NotFoundException("Invite not found.")
    return invite


async def revoke(db: AsyncSession, invite: ProjectInvite) -> None:
    if invite.status != InviteStatus.PENDING:
        raise ConflictException("Only a pending invite can be revoked.")
    invite.status, invite.revoked_at = InviteStatus.REVOKED.value, utcnow()
    await db.commit()


async def resend(db: AsyncSession, invite: ProjectInvite, project: Project, inviter: dict[str, Any]) -> str:
    """A fresh token and expiry; the old link stops working."""
    if invite.status != InviteStatus.PENDING:
        raise ConflictException("Accepted and revoked invites can't be re-sent; create a new invite.")
    token = secrets.token_urlsafe(32)
    invite.token_hash = hash_token(token)
    invite.expires_at = utcnow() + timedelta(hours=constants.INVITE_TTL_HOURS)
    await _send_invite(db, invite, project, token, inviter["name"])
    await db.commit()
    return token


async def by_token(db: AsyncSession, token: str) -> ProjectInvite:
    invite = await db.scalar(select(ProjectInvite).where(ProjectInvite.token_hash == hash_token(token)))
    if invite is None:
        raise Gone()
    return invite


def email_hint(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'•' * max(len(local) - 1, 1)}@{domain}"


async def _accept(db: AsyncSession, invite: ProjectInvite, user: dict[str, Any]) -> Project:
    """Single use: the row is claimed with a conditional update, so two tabs can't both use it."""
    if invite.status != InviteStatus.PENDING or expired(invite):
        raise Gone()
    if invite.email.lower() != str(user["email"]).lower():
        raise ForbiddenException("This invite is for a different email address. Sign in with the invited account.")
    claimed = await db.execute(
        update(ProjectInvite)
        .where(ProjectInvite.id == invite.id, ProjectInvite.status == InviteStatus.PENDING.value)
        .values(status=InviteStatus.ACCEPTED.value, accepted_at=utcnow(), user_id=user["id"])
        .execution_options(synchronize_session=False)
    )
    if getattr(claimed, "rowcount", 0) != 1:
        raise Gone()
    project = await db.get(Project, invite.project_id)
    if project is None:
        raise Gone()
    await grant_access(db, project, user["id"], invite.grant, "invite", invite.invited_by_id)
    if invite.invited_by_id:
        await notify(
            db,
            [invite.invited_by_id],
            Category.STATUS,
            f"{user['name']} joined {project.code}",
            link=f"/lobby/requests?project={project.id}",
            entity=("project_invite", invite.id),
            actor_id=user["id"],
        )
    await db.commit()
    await db.refresh(invite)
    return project


async def accept(db: AsyncSession, token: str, user: dict[str, Any]) -> Project:
    return await _accept(db, await by_token(db, token), user)


async def join(db: AsyncSession, invite_id: int, user: dict[str, Any]) -> Project:
    """Accept an invite shown in the lobby: the signed-in account's email must be the invited one."""
    invite = await db.get(ProjectInvite, invite_id)
    if invite is None or invite.email.lower() != str(user["email"]).lower():
        raise NotFoundException("Invite not found.")
    return await _accept(db, invite, user)


async def claim_invites(db: AsyncSession, user: dict[str, Any]) -> list[Project]:
    """At first sign-in: join every project whose invite created this account."""
    rows = (
        await db.execute(
            select(ProjectInvite).where(
                ProjectInvite.user_id == user["id"],
                ProjectInvite.created_account.is_(True),
                ProjectInvite.status == InviteStatus.PENDING.value,
                ProjectInvite.expires_at > utcnow(),
            )
        )
    ).scalars()
    joined = []
    for invite in list(rows):
        try:
            joined.append(await _accept(db, invite, user))
        except (Gone, ForbiddenException):
            await db.rollback()
    return joined


async def my_requests(db: AsyncSession, user_id: int) -> list[AccessRequest]:
    since = utcnow() - PANEL_WINDOW
    rows = await db.execute(
        select(AccessRequest)
        .where(
            AccessRequest.user_id == user_id,
            (AccessRequest.status == RequestStatus.PENDING.value)
            | (func.coalesce(AccessRequest.decided_at, AccessRequest.withdrawn_at) >= since),
        )
        .order_by(AccessRequest.id.desc())
    )
    latest: dict[int, AccessRequest] = {}
    for r in rows.scalars():
        latest.setdefault(r.project_id, r)
    return list(latest.values())
