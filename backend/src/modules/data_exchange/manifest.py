from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="data_exchange",
    version="0.1.0",
    display_name="Import and Export",
    description="Export any module's records to Excel, CSV or PDF, and import budgets, tasks and contacts from spreadsheets.",
    depends=("projects",),
    route_prefix="/data",
)
