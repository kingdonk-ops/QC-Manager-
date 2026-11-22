from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="cde",
    version="0.1.0",
    display_name="CDE",
    description="ISO 19650 common data environment: naming convention, WIP/Shared/Published/Archived states, "
    "suitability codes, P/C revisions and approval gates.",
    depends=("projects", "files", "notifications"),
)
