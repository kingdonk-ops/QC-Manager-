from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="comments",
    version="0.1.0",
    display_name="Comments",
    description="Threaded comments with @mentions and resolution on any record.",
    category=ModuleCategory.CORE,
    depends=("projects", "notifications"),
)
