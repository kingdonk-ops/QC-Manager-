from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="tasks",
    version="0.1.0",
    display_name="Tasks",
    description="Tasks with a Kanban board, list and calendar views, priorities, due dates and links to any record.",
    depends=("projects", "notifications"),
)
