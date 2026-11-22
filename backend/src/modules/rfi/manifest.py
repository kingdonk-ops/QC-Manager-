from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="rfi",
    version="0.1.0",
    display_name="RFIs",
    description="Requests for information with ball-in-court tracking, threaded responses, impact and due dates.",
    depends=("projects", "contacts", "notifications", "tasks"),
    route_prefix="/rfis",
)
