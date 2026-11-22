from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="schedule",
    version="0.1.0",
    display_name="4D Schedule",
    description="Gantt programme with critical path, baselines, progress, Monte Carlo risk and P6 / MS Project exchange.",
    depends=("projects", "notifications"),
    optional_depends=("cvr",),
)
