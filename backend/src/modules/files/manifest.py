from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="files",
    version="0.1.0",
    display_name="Documents",
    description="Project documents with categories, tags, preview and revisions; attachments on any record.",
    category=ModuleCategory.CORE,
    depends=("projects",),
)
