from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="evm",
    version="0.1.0",
    display_name="Earned Value",
    description="Planned against earned and actual labour hours per work package: SPI, CPI, EAC, S-curves and baselines.",
    depends=("projects",),
    optional_depends=("cvr",),
)
