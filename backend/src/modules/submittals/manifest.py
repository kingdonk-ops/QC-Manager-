from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="submittals",
    version="0.1.0",
    display_name="Submittals",
    description="Submittal register with multi-stage, parallel review workflows, revisions and days outstanding.",
    depends=("projects", "contacts", "files", "notifications"),
)
