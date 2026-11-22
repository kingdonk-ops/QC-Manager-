from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="meetings",
    version="0.1.0",
    display_name="Meetings",
    description="Recurring meeting series, agendas, attendance, action items that become tasks, and issued minutes.",
    depends=("projects", "contacts", "tasks", "notifications"),
)
