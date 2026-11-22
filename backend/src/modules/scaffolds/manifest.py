from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="scaffolds",
    version="0.1.0",
    display_name="Scaffold management",
    description="Scaffold requests, approval, erection, green/yellow/red tags, 7-day and weather inspections, hire days.",
    depends=("projects", "asset_tree", "notifications", "tasks"),
)
