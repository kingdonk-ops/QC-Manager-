from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="people",
    version="0.1.0",
    display_name="Users",
    description="Directory of staff and external users with their roles and teams.",
    category=ModuleCategory.CORE,
    depends=("team",),
)
