from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="portal",
    version="0.1.0",
    display_name="Client Portal",
    description="Invite external users (clients, subcontractors) who sign in with an email and password, "
    "and share plans with the client for review.",
    category=ModuleCategory.PORTAL,
    depends=("team", "projects", "files", "notifications"),
)
