from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="saved_views",
    version="0.1.0",
    display_name="Saved views",
    description="Saved grid views for any register: columns, sort, filters and grouping, personal or shared.",
    depends=("projects", "team"),
)
