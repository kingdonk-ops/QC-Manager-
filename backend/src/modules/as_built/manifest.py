from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="as_built",
    version="0.1.0",
    display_name="As-Built Records",
    description="As-built survey records judged against the inspections acceptance criteria: survey, verify (raising a "
    "workmanship report when out of tolerance) and a signed legal-record attestation.",
    depends=("projects", "asset_tree", "inspections"),
    optional_depends=("ncr",),
)
