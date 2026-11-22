from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="assets",
    version="0.1.0",
    display_name="Asset Register",
    description="Facilities, floors, spaces, product types, components and systems, with Excel import and COBie export.",
    depends=("projects", "contacts", "files"),
)
