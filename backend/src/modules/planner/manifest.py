from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="planner",
    version="0.1.0",
    display_name="Planner",
    description="Look-ahead and shutdown work plans, work packs against work anchors, crews, readiness and daily plans.",
    depends=("projects", "asset_tree", "notifications"),
    optional_depends=("schedule",),
)
