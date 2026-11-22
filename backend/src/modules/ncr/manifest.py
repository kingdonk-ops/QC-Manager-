from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="ncr",
    version="0.1.0",
    display_name="Non-Conformance Reports",
    description="NCRs with root cause, disposition, corrective and preventive actions, cost impact and a PDF report.",
    depends=("projects", "files", "notifications", "contacts"),
)
