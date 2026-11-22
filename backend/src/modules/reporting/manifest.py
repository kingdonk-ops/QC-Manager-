from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="reporting",
    version="0.1.0",
    display_name="Reporting",
    description="KPI and portfolio dashboards, pivots and charts, report templates and scheduled reports by email.",
    depends=("projects",),
    optional_depends=("cvr", "tasks", "contacts", "files"),
)
