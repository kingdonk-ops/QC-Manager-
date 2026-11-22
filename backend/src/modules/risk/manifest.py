from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="risk",
    version="0.1.0",
    display_name="Risk Register",
    description="Project risks scored by probability and impact, with cost exposure, mitigation and review reminders.",
    depends=("projects", "notifications"),
    route_prefix="/risks",
)
