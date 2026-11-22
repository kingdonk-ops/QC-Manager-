from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="workface_log",
    version="0.1.0",
    display_name="Daily Workface Log",
    description="Per crew per day: hours by work anchor or delay code, quantities, delays, equipment, weather, sign-off.",
    depends=("projects", "asset_tree", "planner", "notifications"),
)
