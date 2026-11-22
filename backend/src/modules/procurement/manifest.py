from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="procurement",
    version="0.1.0",
    display_name="Procurement",
    description="Purchase orders to suppliers, emailed as PDF, with goods receipts and committed against received value.",
    depends=("projects", "contacts", "files", "notifications"),
)
