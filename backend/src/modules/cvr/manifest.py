from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="cvr",
    version="0.1.0",
    display_name="Cost-Value Reconciliation",
    description="Cost against value earned per cost head, margins, and a monthly cashflow forecast.",
    depends=("projects",),
)
