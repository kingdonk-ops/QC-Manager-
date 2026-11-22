from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="inspections",
    version="0.1.0",
    display_name="Quality Inspections",
    description="Checklist templates, field inspections with readings and photos, scoring, deficiency follow-up and trends.",
    depends=("projects", "files", "tasks", "notifications"),
    optional_depends=("ncr",),
)
