"""Teams, their members, and the Entra integration's admin routes.

Anyone signed in reads their own teams and the teams they belong to. ``team.*`` permissions cover
every team. A team's leads and managers may also manage its members, up to their own role there.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Path
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from .constants import APP_ROLE_VALUE_MAX_LENGTH, TeamRole
from .dependencies import TeamServiceDep
from .exceptions import NotTeamLeadError, TeamNotFoundError
from .permissions import EntraPermissionName, TeamPermissionName
from .schemas import (
    MembershipSet,
    MyTeamRead,
    RoleMappingRead,
    RoleMappingSet,
    SyncReport,
    TeamCreate,
    TeamDetail,
    TeamRead,
    TeamUpdate,
)
from .service import ROLE_RANK
from .sync_job import sync_all_linked_teams

TeamIdDep = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
UserIdDep = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
AppRoleDep = Annotated[str, Path(min_length=1, max_length=APP_ROLE_VALUE_MAX_LENGTH, pattern=r"^[A-Za-z0-9._-]+$")]

router = APIRouter(tags=["Teams"])
entra_router = APIRouter(tags=["Entra ID"])


@router.get(
    "/",
    response_model=PaginatedListResponse[TeamRead],
    summary="List Teams",
    dependencies=[require_permissions(TeamPermissionName.READ.value)],
)
async def list_teams(
    db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep, page: PageDep = 1, items_per_page: ItemsPerPageDep = 50
) -> dict[str, Any]:
    data = await teams.page(db, compute_offset(page, items_per_page), items_per_page)

    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get("/mine", response_model=list[MyTeamRead], summary="List the Caller's Teams")
async def my_teams(db: AsyncSessionDep, user: CurrentUserDep, teams: TeamServiceDep) -> list[dict[str, Any]]:
    return await teams.mine(db, user["id"])


@router.get(
    "/{team_id}",
    response_model=TeamDetail,
    summary="Get a Team and Its Members",
    description="Open to holders of `team.read` and to the team's own members.",
)
async def get_team(
    team_id: TeamIdDep, db: AsyncSessionDep, user: CurrentUserDep, held: CurrentPermissionsDep, teams: TeamServiceDep
) -> dict[str, Any]:
    if TeamPermissionName.READ.value not in held and await teams.role_in(db, team_id, user["id"]) is None:
        raise TeamNotFoundError("Hidden from non-members")

    return await teams.get(db, team_id)


@router.post(
    "/",
    response_model=TeamRead,
    status_code=201,
    summary="Create a Team",
    dependencies=[require_permissions(TeamPermissionName.CREATE.value)],
)
async def create_team(values: TeamCreate, db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep) -> dict[str, Any]:
    return await teams.create(db, values.model_dump())


@router.patch(
    "/{team_id}",
    response_model=TeamDetail,
    summary="Change a Team",
    dependencies=[require_permissions(TeamPermissionName.UPDATE.value)],
)
async def update_team(
    team_id: TeamIdDep, values: TeamUpdate, db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep
) -> dict[str, Any]:
    return await teams.update(db, team_id, values.model_dump(exclude_unset=True))


@router.delete("/{team_id}", summary="Delete a Team", dependencies=[require_permissions(TeamPermissionName.DELETE.value)])
async def delete_team(team_id: TeamIdDep, db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep) -> dict[str, str]:
    await teams.delete(db, team_id)

    return {"message": "Team deleted"}


async def _may_manage(db: Any, teams: Any, team_id: int, user_id: int, held: frozenset[str], up_to: TeamRole) -> None:
    """Holders of team.manage_members manage anyone; a lead or manager, up to their own role."""
    if TeamPermissionName.MANAGE_MEMBERS.value in held:
        return
    mine = await teams.role_in(db, team_id, user_id)
    if mine is None or mine == TeamRole.MEMBER or ROLE_RANK[up_to] > ROLE_RANK[mine]:
        raise NotTeamLeadError("Not a lead of this team")


@router.put(
    "/{team_id}/members/{user_id}",
    summary="Add a Member or Set Their Role",
    description="On a team linked to an Entra group, only an existing member's role can be set.",
)
async def set_member(
    team_id: TeamIdDep,
    user_id: UserIdDep,
    values: MembershipSet,
    db: AsyncSessionDep,
    caller: CurrentUserDep,
    held: CurrentPermissionsDep,
    teams: TeamServiceDep,
) -> dict[str, str]:
    current = await teams.role_in(db, team_id, user_id)
    highest = max([values.role, current or TeamRole.MEMBER], key=ROLE_RANK.__getitem__)
    await _may_manage(db, teams, team_id, caller["id"], held, highest)
    await teams.set_member(db, team_id, user_id, values.role)

    return {"message": "Membership saved"}


@router.delete(
    "/{team_id}/members/{user_id}", summary="Remove a Member", description="Refused on a team linked to an Entra group."
)
async def remove_member(
    team_id: TeamIdDep,
    user_id: UserIdDep,
    db: AsyncSessionDep,
    caller: CurrentUserDep,
    held: CurrentPermissionsDep,
    teams: TeamServiceDep,
) -> dict[str, str]:
    current = await teams.role_in(db, team_id, user_id) or TeamRole.MEMBER
    await _may_manage(db, teams, team_id, caller["id"], held, current)
    await teams.remove_member(db, team_id, user_id)

    return {"message": "Member removed"}


@entra_router.get(
    "/role-mappings",
    response_model=list[RoleMappingRead],
    summary="List Entra App Role Mappings",
    dependencies=[require_permissions(EntraPermissionName.MANAGE.value)],
)
async def list_role_mappings(db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep) -> list[dict[str, Any]]:
    return await teams.role_mappings(db)


@entra_router.put(
    "/role-mappings/{app_role_value}",
    response_model=RoleMappingRead,
    summary="Map an Entra App Role",
    description="Users holding this app role in Entra hold the role from their next sign-in; others lose it.",
    dependencies=[require_permissions(EntraPermissionName.MANAGE.value)],
)
async def set_role_mapping(
    app_role_value: AppRoleDep, values: RoleMappingSet, db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep
) -> dict[str, Any]:
    return await teams.set_role_mapping(db, app_role_value, values.role_id)


@entra_router.delete(
    "/role-mappings/{app_role_value}",
    summary="Unmap an Entra App Role",
    dependencies=[require_permissions(EntraPermissionName.MANAGE.value)],
)
async def delete_role_mapping(
    app_role_value: AppRoleDep, db: AsyncSessionDep, _: CurrentUserDep, teams: TeamServiceDep
) -> dict[str, str]:
    await teams.delete_role_mapping(db, app_role_value)

    return {"message": "Mapping removed"}


@entra_router.post(
    "/sync",
    response_model=SyncReport,
    summary="Sync Linked Teams from Entra Now",
    dependencies=[require_permissions(EntraPermissionName.MANAGE.value)],
)
async def sync_now(db: AsyncSessionDep, _: CurrentUserDep) -> SyncReport:
    return await sync_all_linked_teams(db)
