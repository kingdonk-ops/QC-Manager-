from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="coatings",
    version="0.1.0",
    display_name="Coatings",
    description="Coating systems, jobs with surface-prep and per-coat hold points, dew-point checks and DFT statistics.",
    depends=("projects", "asset_tree", "notifications"),
    optional_depends=("calibration",),
)
