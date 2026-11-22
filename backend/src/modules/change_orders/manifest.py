from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="change_orders",
    version="0.1.0",
    display_name="Change Orders",
    description="Variations priced line by line, approved through a workflow, optionally applied to the CVR forecast.",
    depends=("projects", "notifications"),
    optional_depends=("cvr",),
)
