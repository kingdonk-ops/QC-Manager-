from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="change_of_scope",
    version="0.1.0",
    display_name="Change of Scope",
    description="Field-raised change cards on the asset breakdown: client acknowledgement and approval, a 14-day "
    "expiry with reminders, and conversion to an approved change order.",
    depends=("projects", "notifications", "asset_tree"),
    optional_depends=("change_orders",),
)
