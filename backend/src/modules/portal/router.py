"""Inviting and listing the portal's external users."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from ...infrastructure.auth.authorization import require_permissions
from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import MAX_INTEGER_ID
from .permissions import PortalPermissionName
from .review_router import review_router
from .schemas import ExternalUserRead, InvitationCreate
from .service import PortalService

router = APIRouter(tags=["Client Portal"])

PortalServiceDep = Annotated[PortalService, Depends(PortalService)]
UserIdDep = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
INVITE = [require_permissions(PortalPermissionName.INVITE.value)]
router.include_router(review_router)


@router.post(
    "/invitations",
    response_model=ExternalUserRead,
    status_code=201,
    summary="Invite an External User",
    description="Creates the account and emails a link to set its password. The account can't sign in until then.",
    dependencies=INVITE,
)
async def invite(values: InvitationCreate, db: AsyncSessionDep, _: CurrentUserDep, portal: PortalServiceDep) -> dict[str, Any]:
    return await portal.invite(db, values.name, str(values.email), values.team_ids)


@router.get("/users", response_model=list[ExternalUserRead], summary="List External Users", dependencies=INVITE)
async def list_external_users(db: AsyncSessionDep, _: CurrentUserDep, portal: PortalServiceDep) -> list[dict[str, Any]]:
    return await portal.list(db)


@router.post("/users/{user_id}/resend-invitation", summary="Resend the Set-Password Link", dependencies=INVITE)
async def resend(user_id: UserIdDep, db: AsyncSessionDep, _: CurrentUserDep, portal: PortalServiceDep) -> dict[str, str]:
    await portal.resend(db, user_id)

    return {"message": "Invitation sent"}
