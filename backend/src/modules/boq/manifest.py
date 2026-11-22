from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="boq",
    version="0.1.0",
    display_name="Bill of Quantities",
    description="Hierarchical bills of quantities priced from a resource catalog and assemblies, with validation, "
    "undo/redo, and Excel, CSV and GAEB exchange.",
    depends=("projects",),
    optional_depends=("contacts",),
)
