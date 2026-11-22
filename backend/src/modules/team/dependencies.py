from typing import Annotated

from fastapi import Depends

from .service import TeamService


def get_team_service() -> TeamService:
    return TeamService()


TeamServiceDep = Annotated[TeamService, Depends(get_team_service)]
