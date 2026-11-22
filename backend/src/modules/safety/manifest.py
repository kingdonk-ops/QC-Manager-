from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="safety",
    version="0.1.0",
    display_name="Safety",
    description="Incidents and observations with a 5x5 risk matrix, corrective actions, hours worked and TRIR/LTIFR.",
    depends=("projects", "files", "notifications"),
)
