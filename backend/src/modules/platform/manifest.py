from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="platform",
    version="0.1.0",
    display_name="Platform",
    description="Module switches, per-user module access, built-in roles and onboarding.",
    category=ModuleCategory.CORE,
)
