"""Mounted at /api/v1/platform."""

from typing import Annotated, Any

from fastapi import APIRouter, Path
from sqlalchemy import delete, select

from ...infrastructure.auth.authorization import load_permissions, require_permissions
from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import NotFoundException, UnprocessableEntityException
from ...infrastructure.modules.loader import installed_modules
from ..common.pagination import MAX_INTEGER_ID
from ..user.models import User
from .access import AccessLevel, levels_of, module_permissions
from .models import ModuleAccess, UserPreference
from .permissions import PlatformPermissionName
from .schemas import AccessSet, ModuleAccessRow, PreferenceSet, PresetApply

router = APIRouter(tags=["Platform"])

UserId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]
PrefKey = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=64)]
ACCESS = [require_permissions(PlatformPermissionName.ACCESS.value)]


def _gated_modules() -> list[tuple[str, str]]:
    """Modules that declare permissions, which is what an access level can act on."""
    return [
        (m.manifest.name, m.manifest.display_name)
        for m in installed_modules()
        if m.enabled and module_permissions(m.manifest.name)
    ]


async def _rows(db: Any, user_id: int) -> list[ModuleAccessRow]:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundException("No such user")
    levels = await levels_of(db, user_id)
    held = await load_permissions(db, user_id, is_superuser=user.is_superuser)

    return [
        ModuleAccessRow(
            module=name,
            display_name=display,
            level=levels.get(name),
            effective=sorted(held & module_permissions(name)),
        )
        for name, display in _gated_modules()
    ]


@router.get("/access/{user_id}", response_model=list[ModuleAccessRow], summary="A User's Module Access", dependencies=ACCESS)
async def get_access(user_id: UserId, db: AsyncSessionDep, _: CurrentUserDep) -> list[ModuleAccessRow]:
    return await _rows(db, user_id)


async def _apply(db: Any, user_id: int, levels: dict[str, AccessLevel | None]) -> None:
    known = {name for name, _ in _gated_modules()}
    unknown = set(levels) - known
    if unknown:
        raise UnprocessableEntityException(f"Unknown modules: {', '.join(sorted(unknown))}")
    for module, level in levels.items():
        await db.execute(delete(ModuleAccess).where(ModuleAccess.user_id == user_id, ModuleAccess.module == module))
        if level is not None:
            db.add(ModuleAccess(user_id=user_id, module=module, level=level.value))
    await db.commit()


@router.put(
    "/access/{user_id}",
    response_model=list[ModuleAccessRow],
    summary="Set a User's Module Access",
    description="`null` for a module removes its level, so the user's roles decide again.",
    dependencies=ACCESS,
)
async def set_access(user_id: UserId, values: AccessSet, db: AsyncSessionDep, caller: CurrentUserDep) -> list[ModuleAccessRow]:
    if user_id == caller["id"]:
        raise UnprocessableEntityException("You can't change your own module access.")
    await _rows(db, user_id)
    await _apply(db, user_id, values.levels)

    return await _rows(db, user_id)


@router.post(
    "/access/{user_id}/preset",
    response_model=list[ModuleAccessRow],
    summary="Apply an Access Preset",
    description="`full`: Full on every module. `view_only`: View on every module. `minimal`: View on Projects, "
    "None elsewhere. `clear`: remove every level, so roles decide.",
    dependencies=ACCESS,
)
async def apply_preset(
    user_id: UserId, values: PresetApply, db: AsyncSessionDep, caller: CurrentUserDep
) -> list[ModuleAccessRow]:
    if user_id == caller["id"]:
        raise UnprocessableEntityException("You can't change your own module access.")
    await _rows(db, user_id)
    modules = [name for name, _ in _gated_modules()]
    preset: dict[str, AccessLevel | None]
    if values.preset == "full":
        preset = dict.fromkeys(modules, AccessLevel.FULL)
    elif values.preset == "view_only":
        preset = dict.fromkeys(modules, AccessLevel.VIEW)
    elif values.preset == "minimal":
        preset = {m: AccessLevel.VIEW if m == "projects" else AccessLevel.NONE for m in modules}
    else:
        preset = dict.fromkeys(modules, None)
    await _apply(db, user_id, preset)

    return await _rows(db, user_id)


@router.get("/me/preferences", summary="All of the Caller's Preferences")
async def my_preferences(db: AsyncSessionDep, user: CurrentUserDep) -> dict[str, Any]:
    rows = await db.execute(select(UserPreference.key, UserPreference.value).where(UserPreference.user_id == user["id"]))

    return {key: value for key, value in rows.all()}


@router.put("/me/preferences/{key}", summary="Set One of the Caller's Preferences")
async def set_preference(key: PrefKey, values: PreferenceSet, db: AsyncSessionDep, user: CurrentUserDep) -> dict[str, Any]:
    pref = await db.get(UserPreference, (user["id"], key))
    if pref is None:
        db.add(UserPreference(user_id=user["id"], key=key, value=values.value))
    else:
        pref.value = values.value
    await db.commit()

    return {key: values.value}
