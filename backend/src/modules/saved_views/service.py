"""Who sees and changes which saved view.

* ``private``: the owner only. ``project``: everyone who can read the project. ``team``: the owner, managers
  (``saved_views.manage``) and the members of any of the view's teams.
* Changing or deleting: the owner; a shared view also a manager.
* Sharing (``project`` / ``team``) needs ``saved_views.share``; setting or clearing the project default needs
  ``saved_views.manage``. Team views can't be defaults.
* At most one private default per owner and register, and one project default per register: setting a default
  clears the previous one. Changing a view's visibility without saying ``is_default`` drops its default flag.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, delete, false, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..team.models import Team, TeamMembership
from ..user.models import User
from .models import SavedView, SavedViewTeam
from .permissions import SavedViewPermissionName as P


class ViewNotFound(ResourceNotFoundError):
    public_detail = "Saved view not found."


class ViewRuleError(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class ViewForbidden(PermissionDeniedError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


@dataclass(frozen=True)
class Viewer:
    user_id: int
    held: frozenset[str]
    team_ids: frozenset[int]

    @property
    def manager(self) -> bool:
        return P.MANAGE.value in self.held


async def viewer(db: AsyncSession, user_id: int, held: frozenset[str]) -> Viewer:
    teams = (await db.execute(select(TeamMembership.team_id).where(TeamMembership.user_id == user_id))).scalars()
    return Viewer(user_id, held, frozenset(teams))


def visible_filter(v: Viewer) -> Any:
    shared_with_my_teams = SavedView.id.in_(select(SavedViewTeam.view_id).where(SavedViewTeam.team_id.in_(v.team_ids or {0})))
    return or_(
        SavedView.owner_id == v.user_id,
        SavedView.visibility == "project",
        and_(SavedView.visibility == "team", shared_with_my_teams),
        and_(SavedView.visibility != "private", true() if v.manager else false()),
    )


def can_edit(v: Viewer, view: SavedView) -> bool:
    if view.owner_id == v.user_id:
        return P.CREATE.value in v.held
    return view.visibility != "private" and v.manager


async def team_ids(db: AsyncSession, view_ids: Collection[int]) -> dict[int, list[int]]:
    found: dict[int, list[int]] = {i: [] for i in view_ids}
    if view_ids:
        rows = await db.execute(
            select(SavedViewTeam.view_id, SavedViewTeam.team_id)
            .where(SavedViewTeam.view_id.in_(list(view_ids)))
            .order_by(SavedViewTeam.team_id)
        )
        for view_id, team_id in rows.tuples():
            found[view_id].append(team_id)
    return found


async def present(db: AsyncSession, v: Viewer, views: list[SavedView]) -> list[dict[str, Any]]:
    teams = await team_ids(db, [x.id for x in views])
    owners = {x.owner_id for x in views}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(owners)))).tuples().all()) if owners else {}
    return [
        {
            "id": x.id,
            "project_id": x.project_id,
            "register_key": x.register_key,
            "name": x.name,
            "owner_id": x.owner_id,
            "owner_name": names.get(x.owner_id),
            "visibility": x.visibility,
            "team_ids": teams[x.id],
            "is_default": x.is_default,
            "config": x.config,
            "can_edit": can_edit(v, x),
            "updated_at": x.updated_at,
        }
        for x in views
    ]


async def get_visible(db: AsyncSession, v: Viewer, view_id: int) -> SavedView:
    view = await db.scalar(select(SavedView).where(SavedView.id == view_id, visible_filter(v)))
    if view is None:
        raise ViewNotFound(str(view_id))
    return view


async def _check(
    db: AsyncSession, v: Viewer, visibility: str, teams: list[int] | None, is_default: bool, *, sharing: bool = True
) -> None:
    if sharing and visibility != "private" and P.SHARE.value not in v.held and not v.manager:
        raise ViewForbidden("Sharing a view needs the saved_views.share permission.")
    if visibility == "team":
        if not teams:
            raise ViewRuleError("Name at least one team to share the view with.")
        found = set((await db.execute(select(Team.id).where(Team.id.in_(teams)))).scalars())
        if missing := sorted(set(teams) - found):
            raise ViewRuleError(f"No team {', '.join(map(str, missing))}.")
    elif teams:
        raise ViewRuleError("Only a team view names teams.")
    if is_default and visibility == "team":
        raise ViewRuleError("A team view can't be a default; make it a project view or keep it private.")
    if sharing and is_default and visibility == "project" and not v.manager:
        raise ViewForbidden("Setting the project default needs the saved_views.manage permission.")


async def _clear_other_defaults(db: AsyncSession, view: SavedView) -> None:
    if not view.is_default:
        return
    same = [
        SavedView.project_id == view.project_id,
        SavedView.register_key == view.register_key,
        SavedView.visibility == view.visibility,
        SavedView.id != view.id,
    ]
    if view.visibility == "private":
        same.append(SavedView.owner_id == view.owner_id)
    await db.execute(update(SavedView).where(*same).values(is_default=False).execution_options(synchronize_session=False))


async def _set_teams(db: AsyncSession, view: SavedView, teams: list[int]) -> None:
    await db.execute(delete(SavedViewTeam).where(SavedViewTeam.view_id == view.id))
    db.add_all([SavedViewTeam(view_id=view.id, team_id=t) for t in sorted(set(teams))])


async def create(db: AsyncSession, v: Viewer, values: dict[str, Any]) -> SavedView:
    teams = values.pop("team_ids", [])
    await _check(db, v, values["visibility"], teams, values["is_default"])
    view = SavedView(owner_id=v.user_id, **values)
    db.add(view)
    await db.flush()
    await _set_teams(db, view, teams if view.visibility == "team" else [])
    await _clear_other_defaults(db, view)
    await db.flush()
    return view


async def change(db: AsyncSession, v: Viewer, view: SavedView, values: dict[str, Any]) -> SavedView:
    if not can_edit(v, view):
        raise ViewForbidden("Only the owner (or a manager, for a shared view) can change this view.")
    visibility = values.get("visibility", view.visibility)
    if visibility != view.visibility and "is_default" not in values:
        values["is_default"] = False
    is_default = values.get("is_default", view.is_default)
    current = (await team_ids(db, [view.id]))[view.id]
    teams = values.pop("team_ids", None)
    if teams is None:
        teams = current if visibility == "team" else []
    was_project_default = view.visibility == "project" and view.is_default
    becomes_project_default = visibility == "project" and is_default
    if was_project_default != becomes_project_default and not v.manager:
        raise ViewForbidden("Changing the project default needs the saved_views.manage permission.")
    widened = visibility != view.visibility or set(teams) - set(current)
    await _check(db, v, visibility, teams, is_default, sharing=bool(widened))
    for key, value in values.items():
        if value is None:  # an explicit null leaves the field alone
            continue
        setattr(view, key, value)
    await _set_teams(db, view, teams if visibility == "team" else [])
    await _clear_other_defaults(db, view)
    await db.flush()
    return view


async def remove(db: AsyncSession, v: Viewer, view: SavedView) -> None:
    if not can_edit(v, view):
        raise ViewForbidden("Only the owner (or a manager, for a shared view) can delete this view.")
    await db.delete(view)
    await db.flush()


async def default_view(db: AsyncSession, v: Viewer, project_id: int, register_key: str) -> SavedView | None:
    """The caller's own default for the register, else the project default, else none."""
    base = [SavedView.project_id == project_id, SavedView.register_key == register_key, SavedView.is_default.is_(True)]
    mine = await db.scalar(select(SavedView).where(*base, SavedView.visibility == "private", SavedView.owner_id == v.user_id))
    return mine or await db.scalar(select(SavedView).where(*base, SavedView.visibility == "project"))
