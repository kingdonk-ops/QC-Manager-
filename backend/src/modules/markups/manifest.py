from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="markups",
    version="0.1.0",
    display_name="PDF Markups",
    description="Mark up drawings: clouds, arrows, notes, stamps and scaled measurements, printed onto the PDF.",
    depends=("projects", "files", "notifications"),
)
