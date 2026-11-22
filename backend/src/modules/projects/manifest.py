from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="projects",
    version="0.1.0",
    display_name="Projects",
    description="Projects, their client, and who on the client side may see them in the portal.",
    depends=("team",),
)
