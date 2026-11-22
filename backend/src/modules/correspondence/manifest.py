from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="correspondence",
    version="0.1.0",
    display_name="Correspondence",
    description="Register of letters, emails, notices, instructions and claims, threaded by reply, with response dates.",
    depends=("projects", "contacts"),
)
