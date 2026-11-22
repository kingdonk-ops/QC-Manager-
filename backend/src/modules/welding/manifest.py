from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="welding",
    version="0.1.0",
    display_name="Welding & NDE",
    description="Weld register, WPS/PQR, welder qualifications, NDE sampling and repairs, bolted joints.",
    depends=("projects", "asset_tree", "files"),
    optional_depends=("calibration", "materials"),
)
