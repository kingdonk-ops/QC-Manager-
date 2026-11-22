"""Teams and their members as datasets."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, register_dataset
from ..user.models import User
from .constants import TeamRole
from .models import Team, TeamMembership


async def team_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    teams = list((await db.execute(select(Team).order_by(Team.name))).scalars())
    members = (await db.execute(select(TeamMembership.team_id, TeamMembership.role))).all()
    return [
        {
            "name": t.name,
            "description": t.description,
            "entra_linked": t.entra_group_id is not None,
            "members": sum(1 for team_id, _ in members if team_id == t.id),
            "leads": sum(1 for team_id, role in members if team_id == t.id and role != TeamRole.MEMBER.value),
        }
        for t in teams
    ]


async def member_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(Team.name, User.name, User.email, TeamMembership.role)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .join(User, User.id == TeamMembership.user_id)
        .order_by(Team.name, User.name)
    )
    return [{"team": team, "name": name, "email": email, "role": role} for team, name, email, role in rows.all()]


register_dataset(
    Dataset(
        name="teams",
        module="team",
        title="Teams",
        description="Teams with their member and lead counts.",
        project_scoped=False,
        permission="team.read",
        columns=[
            Column("name", "Team"),
            Column("description", "Description"),
            Column("entra_linked", "From Entra", "bool"),
            Column("members", "Members", "number"),
            Column("leads", "Leads and managers", "number"),
        ],
        rows=team_rows,
    )
)

register_dataset(
    Dataset(
        name="team_members",
        module="team",
        title="Team members",
        description="Who is in which team, and their role there.",
        project_scoped=False,
        permission="team.read",
        columns=[Column("team", "Team"), Column("name", "Name"), Column("email", "Email"), Column("role", "Role")],
        rows=member_rows,
    )
)
