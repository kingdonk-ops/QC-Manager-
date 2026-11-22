from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="materials",
    version="0.1.0",
    display_name="Materials & Traceability",
    description="Receipts, heats with mill certificates, PMI, quarantine holds, issue to work, two-way traceability.",
    depends=("projects", "asset_tree", "files"),
    optional_depends=("procurement", "calibration"),
)
