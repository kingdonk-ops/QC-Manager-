"""``GET /api/v1/modules``: which business modules this deployment runs, for the UI to build its menu."""

from fastapi import APIRouter
from pydantic import BaseModel

from ..auth.deps import CurrentUserDep
from .loader import installed_modules

router = APIRouter(tags=["Modules"])


class ModuleRead(BaseModel):
    name: str
    version: str
    display_name: str
    description: str
    category: str
    depends: list[str]
    enabled: bool
    api_prefix: str


@router.get("", response_model=list[ModuleRead], summary="List Installed Modules")
async def list_modules(_: CurrentUserDep) -> list[ModuleRead]:
    return [
        ModuleRead(
            name=m.manifest.name,
            version=m.manifest.version,
            display_name=m.manifest.display_name,
            description=m.manifest.description,
            category=m.manifest.category.value,
            depends=list(m.manifest.depends),
            enabled=m.enabled,
            api_prefix=f"/api/v1{m.manifest.prefix}",
        )
        for m in installed_modules()
    ]
