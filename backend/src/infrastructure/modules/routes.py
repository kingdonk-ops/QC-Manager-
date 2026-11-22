"""The module administration API: what's installed, what's on, and switching modules at runtime."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.common.schemas import EncodableText
from ..audit_ledger import record_audit
from ..auth.authorization import require_permissions
from ..auth.deps import CurrentUserDep
from ..database.session import async_session
from ..http_exceptions import NotFoundException, UnprocessableEntityException
from .loader import dependencies_of, dependents_of, installed_modules
from .models import ModuleSetting
from .state import invalidate, is_enabled, switches

router = APIRouter(tags=["Modules"])

DbDep = Annotated[AsyncSession, Depends(async_session)]
ModuleName = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]


class ModuleRead(BaseModel):
    name: str
    version: str
    display_name: str
    description: str
    category: str
    core: bool
    depends: list[str]
    dependents: list[str]
    installed: bool
    enabled: bool
    api_prefix: str


class ModuleToggle(EncodableText):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    cascade: bool = False
    """Also switch off the modules that depend on this one (when disabling), or switch on what it needs (when enabling)."""


class ToggleResult(BaseModel):
    changed: list[str]
    modules: list[ModuleRead]


class DependencyRead(BaseModel):
    name: str
    depends: list[str]
    dependents: list[str]
    enabled_dependents: list[str]
    disabled_dependencies: list[str]


async def _read_all(db: AsyncSession, project_id: int | None) -> list[ModuleRead]:
    out = []
    for m in installed_modules():
        out.append(
            ModuleRead(
                name=m.manifest.name,
                version=m.manifest.version,
                display_name=m.manifest.display_name,
                description=m.manifest.description,
                category=m.manifest.category.value,
                core=m.manifest.core,
                depends=list(m.manifest.depends),
                dependents=list(dependents_of(m.manifest.name)),
                installed=m.enabled,
                enabled=await is_enabled(db, m.manifest.name, project_id),
                api_prefix=f"/api/v1{m.manifest.prefix}",
            )
        )
    return out


@router.get("", response_model=list[ModuleRead], summary="List Modules and Whether They're On")
async def list_modules(
    db: DbDep,
    _: CurrentUserDep,
    project_id: Annotated[int | None, Query(ge=1, description="Apply this project's overrides")] = None,
) -> list[ModuleRead]:
    """``installed`` is false for a module the deployment left out (``MODULES_DISABLED``);
    ``enabled`` is the runtime switch, with the project's override when ``project_id`` is given."""
    return await _read_all(db, project_id)


@router.get("/{name}/dependencies", response_model=DependencyRead, summary="What a Module Needs and What Needs It")
async def module_dependencies(name: ModuleName, db: DbDep, _: CurrentUserDep) -> DependencyRead:
    if name not in {m.manifest.name for m in installed_modules()}:
        raise NotFoundException("No such module")
    state = await switches(db)
    dependents = dependents_of(name)
    depends = dependencies_of(name)

    return DependencyRead(
        name=name,
        depends=list(depends),
        dependents=list(dependents),
        enabled_dependents=[d for d in dependents if state.get(d)],
        disabled_dependencies=[d for d in depends if not state.get(d)],
    )


@router.patch(
    "/{name}/toggle",
    response_model=ToggleResult,
    summary="Switch a Module On or Off",
    description="""
        Switching a module off hides it and answers 404 on its API; its data stays. A module other
        enabled modules need is refused (422) unless `cascade` is true, which switches them off too.
        Switching on a module whose dependencies are off works the same way. Core modules can't be
        switched off.
        """,
    dependencies=[require_permissions("platform.modules")],
)
async def toggle_module(name: ModuleName, values: ModuleToggle, db: DbDep, user: CurrentUserDep) -> ToggleResult:
    modules = {m.manifest.name: m for m in installed_modules()}
    module = modules.get(name)
    if module is None or not module.enabled:
        raise NotFoundException("No such module, or the deployment leaves it out")
    if module.manifest.core:
        raise UnprocessableEntityException("Core modules are always on.")

    state = await switches(db)
    if values.enabled:
        blockers = [d for d in dependencies_of(name) if not state.get(d)]
        if any(d not in modules or not modules[d].enabled for d in blockers):
            raise UnprocessableEntityException(f"It needs modules this deployment leaves out: {', '.join(blockers)}")
        affected = [*blockers, name]
    else:
        blockers = [d for d in dependents_of(name) if state.get(d)]
        affected = [name, *blockers]
    if blockers and not values.cascade:
        verb = "needs" if values.enabled else "is needed by"
        raise UnprocessableEntityException(f"{name} {verb}: {', '.join(blockers)}. Send cascade=true to change them too.")

    for target in affected:
        await record_audit(
            db,
            "platform.module.toggled",
            "module",
            target,
            actor_id=user["id"],
            summary=f"{target} switched {'on' if values.enabled else 'off'}" + ("" if target == name else f" (with {name})"),
            before={"enabled": state.get(target)},
            after={"enabled": values.enabled},
        )
        setting = await db.get(ModuleSetting, target)
        if setting is None:
            db.add(ModuleSetting(name=target, enabled=values.enabled, updated_by_id=user["id"]))
        else:
            setting.enabled = values.enabled
            setting.updated_by_id = user["id"]
    await db.commit()
    invalidate()

    return ToggleResult(changed=affected, modules=await _read_all(db, None))
