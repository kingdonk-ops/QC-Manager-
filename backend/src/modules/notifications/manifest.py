from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="notifications",
    version="0.1.0",
    display_name="Notifications",
    description="In-app notifications, per-category preferences, and email delivery.",
    category=ModuleCategory.CORE,
)
