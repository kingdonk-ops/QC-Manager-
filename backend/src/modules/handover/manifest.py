from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="handover",
    version="0.1.0",
    display_name="Shift Handover",
    description="Open items, safety notes, permits, equipment and work in progress handed to the incoming supervisor.",
    depends=("projects", "asset_tree", "notifications"),
)
