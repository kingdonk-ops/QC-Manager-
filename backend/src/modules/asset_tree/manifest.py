from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="asset_tree",
    version="0.1.0",
    display_name="Asset hierarchy",
    description="Configurable Site → Area → Asset → RSW → Item breakdown with work anchors, collections and scan tags.",
    depends=("projects",),
)
