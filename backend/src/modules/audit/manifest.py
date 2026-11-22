from ...infrastructure.modules import ModuleManifest
from ...infrastructure.modules.manifest import ModuleCategory

manifest = ModuleManifest(
    name="audit",
    version="0.1.0",
    display_name="Audit ledger",
    description="The append-only, hash-chained record of high-value actions: explorer, export and chain verification.",
    category=ModuleCategory.CORE,
    depends=("projects",),
)
