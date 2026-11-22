from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="transmittals",
    version="0.1.0",
    display_name="Transmittals",
    description="Issue documents to contacts with a cover sheet, revision checks and acknowledgement tracking.",
    depends=("projects", "contacts", "files"),
)
