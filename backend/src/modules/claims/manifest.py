from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="claims",
    version="0.1.0",
    display_name="Progress Claims",
    description="Progress claims from verified completion: schedule of rates on the breakdown, approved variations, "
    "retention, previous payments, certification and a claim PDF.",
    depends=("projects", "notifications", "asset_tree", "schedule"),
    optional_depends=("change_of_scope", "change_orders"),
)
