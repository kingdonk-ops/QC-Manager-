from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="temporary_works",
    version="0.1.0",
    display_name="Temporary Works",
    description="Register of temporary works items with design check categories and the coordinator permits to load "
    "and strike, a bearing-load breach warning, and overdue load and strike rules.",
    depends=("projects", "asset_tree", "notifications", "tasks"),
    optional_depends=("scaffolds",),
)
