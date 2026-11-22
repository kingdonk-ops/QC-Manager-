from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="mdr",
    version="0.1.0",
    display_name="MDR / turnover dossiers",
    description="Dossier builder: scope from the asset tree, section providers, readiness gate, compiled and signed revisions.",
    depends=("projects", "files", "asset_tree", "notifications"),
    optional_depends=("inspections", "ncr", "cde", "numbering"),
)
