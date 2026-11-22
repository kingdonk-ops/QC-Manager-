from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="calibration",
    version="0.1.0",
    display_name="Calibration",
    description="Measuring and test equipment register: certificates, due reminders and a hard gate on readings.",
    depends=("projects", "files", "notifications"),
)
