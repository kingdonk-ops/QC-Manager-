"""Projects, and who may see one. Other modules call ``readable_project`` before serving a project's data."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules import publish
from ..team.exceptions import TeamNotFoundError
from ..team.models import Team, TeamMembership
from .constants import REGIONS
from .exceptions import ProjectCodeTakenError, ProjectNotFoundError
from .models import Project, ProjectModuleOverride
from .permissions import ProjectPermissionName
from .schemas import ProjectRead


def _visible_to(user_id: int, held: frozenset[str]):
    """A filter for the projects this user may read."""
    if ProjectPermissionName.READ.value in held:
        return True
    teams = select(TeamMembership.team_id).where(TeamMembership.user_id == user_id)

    return Project.client_team_id.in_(teams)


async def readable_project(db: AsyncSession, project_id: int, user_id: int, held: frozenset[str]) -> Project:
    """The project, if this user may read it. Otherwise ``ProjectNotFoundError``, so its existence isn't revealed."""
    project = await db.scalar(select(Project).where(Project.id == project_id, _visible_to(user_id, held)))
    if project is None:
        raise ProjectNotFoundError(f"Project {project_id} not found")

    return project


def _read(project: Project) -> dict[str, Any]:
    return ProjectRead.model_validate(project).model_dump(mode="json")


class ProjectService:
    async def page(self, db: AsyncSession, user_id: int, held: frozenset[str], skip: int, limit: int) -> dict[str, Any]:
        visible = _visible_to(user_id, held)
        total = await db.scalar(select(func.count()).select_from(Project).where(visible))
        rows = (await db.execute(select(Project).where(visible).order_by(Project.code).offset(skip).limit(limit))).scalars()

        return {"data": [_read(project) for project in rows], "total_count": total or 0}

    async def get(self, db: AsyncSession, project_id: int, user_id: int, held: frozenset[str]) -> dict[str, Any]:
        return _read(await readable_project(db, project_id, user_id, held))

    async def _check_team(self, db: AsyncSession, team_id: int | None) -> None:
        if team_id is not None and await db.get(Team, team_id) is None:
            raise TeamNotFoundError(f"Team {team_id} not found")

    async def _commit(self, db: AsyncSession) -> None:
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ProjectCodeTakenError("Code taken") from exc

    async def create(self, db: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
        await self._check_team(db, values.get("client_team_id"))
        region = REGIONS.get(values.get("region") or "")
        if not values.get("currency"):
            values["currency"] = region["currency"] if region else "AUD"
        if not values.get("classification_standard") and region:
            values["classification_standard"] = region["classification"]
        project = Project(**values)
        db.add(project)
        await self._commit(db)
        await publish("projects.project.created", {"project_id": project.id})

        return _read(project)

    async def update(self, db: AsyncSession, project_id: int, values: dict[str, Any]) -> dict[str, Any]:
        project = await db.get(Project, project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        if "client_team_id" in values:
            await self._check_team(db, values["client_team_id"])
        for key, value in values.items():
            if value is None and key in {"name", "status", "currency"}:
                continue
            setattr(project, key, value)
        await self._commit(db)
        await publish("projects.project.updated", {"project_id": project.id, "fields": sorted(values)})

        return _read(project)

    async def delete(self, db: AsyncSession, project_id: int) -> None:
        project = await db.get(Project, project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        await db.delete(project)
        await db.commit()
        await publish("projects.project.deleted", {"project_id": project_id})


async def module_override(db: AsyncSession, project_id: int, module: str) -> bool | None:
    """The project's override for a module, or ``None`` when it follows the system-wide switch."""
    override = await db.get(ProjectModuleOverride, (project_id, module))

    return None if override is None else override.enabled


async def overrides_of(db: AsyncSession, project_id: int) -> dict[str, bool]:
    rows = await db.execute(
        select(ProjectModuleOverride.module, ProjectModuleOverride.enabled).where(
            ProjectModuleOverride.project_id == project_id
        )
    )

    return {module: enabled for module, enabled in rows.all()}


async def set_overrides(db: AsyncSession, project_id: int, overrides: dict[str, bool | None]) -> dict[str, bool]:
    for module, enabled in overrides.items():
        current = await db.get(ProjectModuleOverride, (project_id, module))
        if enabled is None:
            if current is not None:
                await db.delete(current)
        elif current is None:
            db.add(ProjectModuleOverride(project_id=project_id, module=module, enabled=enabled))
        else:
            current.enabled = enabled
    await db.commit()

    return await overrides_of(db, project_id)
