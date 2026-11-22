from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="numbering",
    version="0.1.0",
    display_name="Numbering schemes",
    description="Per-project numbering patterns with code lists and never-reused counters for documents, ITPs and dossiers.",
    depends=("projects",),
)
