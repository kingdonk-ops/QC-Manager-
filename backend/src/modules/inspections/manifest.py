from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="inspections",
    version="0.2.0",
    display_name="Quality Inspections",
    description="One inspection engine: checklist and ITP templates, records anchored to the asset tree, Hold/Witness "
    "points, inspection requests (call-outs), review, signing with competency checks, client co-sign and delegation.",
    depends=("projects", "files", "tasks", "notifications", "asset_tree", "contacts"),
    optional_depends=("ncr", "assets"),
)
