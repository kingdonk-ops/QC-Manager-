"""The /api/v1 router: the platform's own features, then every enabled business module."""

from fastapi import APIRouter

from ....infrastructure.modules.loader import mount_module_routers
from ....infrastructure.modules.routes import router as modules_router
from ....wiring.app import API_THROTTLE, ROUTER_MOUNTS

router = APIRouter(prefix="/v1")

for mount in ROUTER_MOUNTS:
    router.include_router(
        mount.router,
        prefix=mount.prefix,
        dependencies=list(API_THROTTLE) if mount.throttled else [],
    )

router.include_router(modules_router, prefix="/modules", dependencies=list(API_THROTTLE))
mount_module_routers(router, list(API_THROTTLE))
