from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="lobby",
    version="0.1.0",
    display_name="Project lobby",
    description="Browse and request access to projects, decide access requests, and invite people to a project by link.",
    depends=("projects", "team", "portal", "notifications"),
)
