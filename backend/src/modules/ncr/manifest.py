from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="ncr",
    version="0.2.0",
    display_name="Issues: punch and NCR",
    description=(
        "One template-driven issues engine with two types: punch (raise, rectify, verify, close; Cat A/B/C) and NCR "
        "(containment, disposition, root cause, CAPA, attested effectiveness verification), with visibility and "
        "MDR-effect flags, upgrades, registers and a PDF report."
    ),
    depends=("projects", "files", "notifications", "contacts", "asset_tree"),
    extra_routers={"/issues": "issues_router"},
)
