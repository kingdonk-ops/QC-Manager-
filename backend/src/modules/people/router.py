"""Mounted at /api/v1/people."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from ..role.permissions import RolePermissionName
from .permissions import PeoplePermissionName
from .schemas import Person, RoleOption
from .service import PeopleService

router = APIRouter(tags=["Users"])

People = Annotated[PeopleService, Depends(PeopleService)]
UserId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


@router.get("/me", response_model=Person, summary="The Signed-in User's Profile, Roles and Teams")
async def me(db: AsyncSessionDep, user: CurrentUserDep, people: People) -> Person:
    return await people.get(db, user["id"])


@router.get(
    "/",
    response_model=PaginatedListResponse[Person],
    summary="List Users with Their Roles and Teams",
    dependencies=[require_permissions(PeoplePermissionName.READ.value)],
)
async def list_people(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    people: People,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 100,
    search: Annotated[str | None, Query(max_length=100)] = None,
    include_inactive: bool = False,
) -> Any:
    data = await people.page(db, compute_offset(page, items_per_page), items_per_page, search, include_inactive)

    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get(
    "/roles",
    response_model=list[RoleOption],
    summary="Roles, and Which Ones Entra Grants",
    dependencies=[require_permissions(RolePermissionName.READ.value)],
)
async def roles(db: AsyncSessionDep, _: CurrentUserDep, people: People) -> list[RoleOption]:
    return await people.roles(db)


@router.get(
    "/{user_id}",
    response_model=Person,
    summary="Get a User",
    dependencies=[require_permissions(PeoplePermissionName.READ.value)],
)
async def get_person(user_id: UserId, db: AsyncSessionDep, _: CurrentUserDep, people: People) -> Person:
    return await people.get(db, user_id)


@router.post(
    "/{user_id}/deactivate",
    response_model=Person,
    summary="Deactivate an Account",
    description="Signs the account out everywhere and refuses every sign-in until reactivated. Nothing is deleted.",
    dependencies=[require_permissions(PeoplePermissionName.MANAGE.value)],
)
async def deactivate(user_id: UserId, db: AsyncSessionDep, caller: CurrentUserDep, people: People) -> Person:
    return await people.set_active(db, user_id, False, caller)


@router.post(
    "/{user_id}/reactivate",
    response_model=Person,
    summary="Reactivate an Account",
    dependencies=[require_permissions(PeoplePermissionName.MANAGE.value)],
)
async def reactivate(user_id: UserId, db: AsyncSessionDep, caller: CurrentUserDep, people: People) -> Person:
    return await people.set_active(db, user_id, True, caller)
