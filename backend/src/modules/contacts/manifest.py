from ...infrastructure.modules import ModuleManifest

manifest = ModuleManifest(
    name="contacts",
    version="0.1.0",
    display_name="Contacts",
    description="Clients, subcontractors, suppliers and consultants, grouped by company and linked to projects.",
    depends=("projects",),
)
