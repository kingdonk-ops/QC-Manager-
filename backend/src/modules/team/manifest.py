from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="team",
    version="0.1.0",
    display_name="Teams",
    description="Teams and memberships, fed from Entra ID groups and app roles.",
    category=ModuleCategory.CORE,
    route_prefix="/teams",
    extra_routers={"/entra": "entra_router"},
)
