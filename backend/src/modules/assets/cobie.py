"""COBie 2.4 handover workbook and its validation.

The workbook has the sheets Contact, Facility, Floor, Space, Zone, Type, Component, System, Document
and Attribute, each with the standard COBie 2.4 column headers in the standard order. Zones and
systems are written one row per member (the zone or system name repeats), as COBie 2.4 expects.
Header cells are coloured with the usual COBie key: yellow required, salmon a reference to another
sheet, purple external, green optional.
"""

import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..contacts.models import Company, Contact, ProjectContact
from ..files.models import StoredFile
from ..projects.models import Project
from .constants import ENTITY_COMPONENT, ENTITY_TYPE
from .models import (
    AssetComponent,
    AssetFacility,
    AssetFloor,
    AssetSpace,
    AssetSystem,
    AssetSystemComponent,
    AssetType,
    AssetZone,
)
from .schemas import CobieIssue, CobieReport, CobieSheetReport

EXT_SYSTEM = "QC Manager"

SHEETS: dict[str, list[str]] = {
    "Contact": (
        "Email CreatedBy CreatedOn Category Company Phone ExtSystem ExtObject ExtIdentifier Department "
        "OrganizationCode GivenName FamilyName Street PostalBox Town StateRegion PostalCode Country"
    ).split(),
    "Facility": (
        "Name CreatedBy CreatedOn Category ProjectName SiteName LinearUnits AreaUnits VolumeUnits CurrencyUnit "
        "AreaMeasurement ExternalSystem ExternalProjectObject ExternalProjectIdentifier ExternalSiteObject "
        "ExternalSiteIdentifier ExternalFacilityObject ExternalFacilityIdentifier Description ProjectDescription "
        "SiteDescription Phase"
    ).split(),
    "Floor": "Name CreatedBy CreatedOn Category ExtSystem ExtObject ExtIdentifier Description Elevation Height".split(),
    "Space": (
        "Name CreatedBy CreatedOn Category FloorName Description ExtSystem ExtObject ExtIdentifier RoomTag "
        "UsableHeight GrossArea NetArea"
    ).split(),
    "Zone": "Name CreatedBy CreatedOn Category SpaceNames ExtSystem ExtObject ExtIdentifier Description".split(),
    "Type": (
        "Name CreatedBy CreatedOn Category Description AssetType Manufacturer ModelNumber WarrantyGuarantorParts "
        "WarrantyDurationParts WarrantyGuarantorLabor WarrantyDurationLabor WarrantyDurationUnit ExtSystem ExtObject "
        "ExtIdentifier ReplacementCost ExpectedLife DurationUnit WarrantyDescription NominalLength NominalWidth "
        "NominalHeight ModelReference Shape Size Color Finish Grade Material Constituents Features "
        "AccessibilityPerformance CodePerformance SustainabilityPerformance"
    ).split(),
    "Component": (
        "Name CreatedBy CreatedOn TypeName Space Description ExtSystem ExtObject ExtIdentifier SerialNumber "
        "InstallationDate WarrantyStartDate TagNumber BarCode AssetIdentifier"
    ).split(),
    "System": "Name CreatedBy CreatedOn Category ComponentNames ExtSystem ExtObject ExtIdentifier Description".split(),
    "Document": (
        "Name CreatedBy CreatedOn Category ApprovalBy Stage SheetName RowName Directory File ExtSystem ExtObject "
        "ExtIdentifier Description Reference"
    ).split(),
    "Attribute": (
        "Name CreatedBy CreatedOn Category SheetName RowName Value Unit ExtSystem ExtObject ExtIdentifier "
        "Description AllowedValues"
    ).split(),
}

REQUIRED = {"Name", "Email", "CreatedBy", "CreatedOn", "Category", "Description", "AssetType"}
REFERENCES = set(
    (
        "CreatedBy Category FloorName SpaceNames Manufacturer WarrantyGuarantorParts WarrantyGuarantorLabor TypeName "
        "Space ComponentNames SheetName RowName Company ProjectName SiteName ApprovalBy Stage Phase"
    ).split()
)
FILLS = {
    "required": PatternFill("solid", fgColor="FFFF99"),
    "reference": PatternFill("solid", fgColor="FFCC99"),
    "external": PatternFill("solid", fgColor="CC99FF"),
    "optional": PatternFill("solid", fgColor="CCFFCC"),
}


def _fill(header: str) -> PatternFill:
    if header.startswith("Ext"):
        return FILLS["external"]
    if header in REFERENCES:
        return FILLS["reference"]
    if header in REQUIRED:
        return FILLS["required"]
    return FILLS["optional"]


def _on(value: datetime | None) -> str:
    return (value or datetime.now()).replace(tzinfo=None, microsecond=0).isoformat()


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


@dataclass
class Register:
    """Everything the workbook and the validation need, loaded once."""

    project: Project
    facilities: list[AssetFacility]
    floors: list[AssetFloor]
    spaces: list[AssetSpace]
    zones: list[AssetZone]
    types: list[AssetType]
    components: list[AssetComponent]
    systems: list[AssetSystem]
    members: dict[int, list[int]]
    contacts: dict[int, Contact]
    companies: dict[int, Company]
    project_contact_ids: set[int]
    documents: list[StoredFile] = field(default_factory=list)


async def load(db: AsyncSession, project: Project) -> Register:
    pid = project.id

    async def rows(model: Any, *order: Any) -> list[Any]:
        return list((await db.scalars(select(model).where(model.project_id == pid).order_by(*order))).all())

    facilities = await rows(AssetFacility, AssetFacility.id)
    floors = await rows(AssetFloor, AssetFloor.position, AssetFloor.elevation, AssetFloor.name)
    spaces = await rows(AssetSpace, AssetSpace.name)
    zones = await rows(AssetZone, AssetZone.name)
    types = await rows(AssetType, AssetType.name)
    components = await rows(AssetComponent, AssetComponent.name)
    systems = await rows(AssetSystem, AssetSystem.name)
    members: dict[int, list[int]] = defaultdict(list)
    if systems:
        result = await db.execute(
            select(AssetSystemComponent.system_id, AssetSystemComponent.component_id).where(
                AssetSystemComponent.system_id.in_([s.id for s in systems])
            )
        )
        for sid, cid in result.tuples().all():
            members[sid].append(cid)
    project_contact_ids = set(
        (await db.scalars(select(ProjectContact.contact_id).where(ProjectContact.project_id == pid))).all()
    )
    contact_ids = project_contact_ids | {
        c for t in types for c in (t.manufacturer_id, t.warranty_guarantor_id) if c is not None
    }
    contacts = (
        {c.id: c for c in (await db.scalars(select(Contact).where(Contact.id.in_(contact_ids)))).all()} if contact_ids else {}
    )
    company_ids = {c.company_id for c in contacts.values() if c.company_id}
    companies = (
        {c.id: c for c in (await db.scalars(select(Company).where(Company.id.in_(company_ids)))).all()} if company_ids else {}
    )
    entity_ids = {ENTITY_COMPONENT: [c.id for c in components], ENTITY_TYPE: [t.id for t in types]}
    documents: list[StoredFile] = []
    for entity_type, ids in entity_ids.items():
        if ids:
            documents += (
                await db.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.entity_type == entity_type,
                        StoredFile.entity_id.in_(ids),
                        StoredFile.is_latest.is_(True),
                        StoredFile.project_id == pid,
                    )
                    .order_by(StoredFile.name)
                )
            ).all()
    return Register(
        project=project,
        facilities=facilities,
        floors=floors,
        spaces=spaces,
        zones=zones,
        types=types,
        components=components,
        systems=systems,
        members=members,
        contacts=contacts,
        companies=companies,
        project_contact_ids=project_contact_ids,
        documents=documents,
    )


def contact_key(contact: Contact) -> str:
    """The Contact sheet's key is the email; a contact without one gets a stand-in."""
    return contact.email or f"contact-{contact.id}@unknown.invalid"


def build_rows(reg: Register, created_by: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {name: [] for name in SHEETS}
    floor_by_id = {f.id: f for f in reg.floors}
    space_by_id = {s.id: s for s in reg.spaces}
    type_by_id = {t.id: t for t in reg.types}
    component_by_id = {c.id: c for c in reg.components}

    def email(contact_id: int | None) -> str | None:
        contact = reg.contacts.get(contact_id) if contact_id else None
        return contact_key(contact) if contact else None

    def base(name: str, created: datetime | None) -> dict[str, Any]:
        return {"Name": name, "CreatedBy": created_by, "CreatedOn": _on(created)}

    def ext(obj: str, ident: int) -> dict[str, Any]:
        return {"ExtSystem": EXT_SYSTEM, "ExtObject": obj, "ExtIdentifier": str(ident)}

    emails = {contact_key(c) for c in reg.contacts.values()}
    if created_by not in emails:
        out["Contact"].append(
            {"Email": created_by, "CreatedBy": created_by, "CreatedOn": _on(None), "Category": "Information Manager"}
        )
    for person in sorted(reg.contacts.values(), key=contact_key):
        company = reg.companies.get(person.company_id) if person.company_id else None
        out["Contact"].append(
            {
                "Email": contact_key(person),
                "CreatedBy": created_by,
                "CreatedOn": _on(person.created_at),
                "Category": person.type,
                "Company": company.name if company else None,
                "Phone": person.phone or person.mobile or (company.phone if company else None),
                **ext("Contact", person.id),
                "Department": person.job_title,
                "GivenName": person.first_name,
                "FamilyName": person.last_name,
                "Street": company.address if company else None,
            }
        )

    project = reg.project
    for f in reg.facilities:
        out["Facility"].append(
            {
                **base(f.name, f.created_at),
                "Category": f.category,
                "ProjectName": project.name,
                "SiteName": f.site_name or project.location,
                "LinearUnits": f.linear_units,
                "AreaUnits": f.area_units,
                "VolumeUnits": f.volume_units,
                "CurrencyUnit": project.currency,
                "AreaMeasurement": f.area_measurement,
                "ExternalSystem": EXT_SYSTEM,
                "ExternalProjectObject": "Project",
                "ExternalProjectIdentifier": project.code,
                "ExternalFacilityObject": "Facility",
                "ExternalFacilityIdentifier": str(f.id),
                "Description": f.description or f.name,
                "ProjectDescription": project.description or project.name,
                "Phase": f.phase,
            }
        )
    for fl in reg.floors:
        out["Floor"].append(
            {
                **base(fl.name, fl.created_at),
                "Category": fl.category,
                **ext("Floor", fl.id),
                "Description": fl.description or fl.name,
                "Elevation": fl.elevation,
                "Height": fl.height,
            }
        )
    for s in reg.spaces:
        floor = floor_by_id.get(s.floor_id)
        out["Space"].append(
            {
                **base(s.name, s.created_at),
                "Category": s.category,
                "FloorName": floor.name if floor else None,
                "Description": s.description or s.name,
                **ext("Space", s.id),
                "RoomTag": s.room_tag,
                "UsableHeight": s.usable_height,
                "GrossArea": s.gross_area,
                "NetArea": s.net_area,
            }
        )
    for z in reg.zones:
        names: list[str | None] = [space_by_id[i].name for i in z.space_ids if i in space_by_id]
        for space_name in names or [None]:
            out["Zone"].append(
                {
                    **base(z.name, z.created_at),
                    "Category": z.category,
                    "SpaceNames": space_name,
                    **ext("Zone", z.id),
                    "Description": z.description or z.name,
                }
            )
    for t in reg.types:
        out["Type"].append(
            {
                **base(t.name, t.created_at),
                "Category": t.category,
                "Description": t.description or t.name,
                "AssetType": t.asset_kind,
                "Manufacturer": email(t.manufacturer_id),
                "ModelNumber": t.model_number,
                "WarrantyGuarantorParts": email(t.warranty_guarantor_id or t.manufacturer_id),
                "WarrantyDurationParts": t.warranty_duration_parts,
                "WarrantyGuarantorLabor": email(t.warranty_guarantor_id or t.manufacturer_id),
                "WarrantyDurationLabor": t.warranty_duration_labor,
                "WarrantyDurationUnit": t.warranty_duration_unit,
                **ext("Type", t.id),
                "ReplacementCost": float(t.replacement_cost) if t.replacement_cost is not None else None,
                "ExpectedLife": t.expected_life,
                "DurationUnit": t.duration_unit,
                "WarrantyDescription": t.warranty_description,
                "NominalLength": t.nominal_length,
                "NominalWidth": t.nominal_width,
                "NominalHeight": t.nominal_height,
                "ModelReference": t.model_reference,
                "Shape": t.shape,
                "Size": t.size,
                "Color": t.color,
                "Finish": t.finish,
                "Grade": t.grade,
                "Material": t.material,
            }
        )
    for c in reg.components:
        ctype = type_by_id.get(c.type_id) if c.type_id else None
        space = space_by_id.get(c.space_id) if c.space_id else None
        out["Component"].append(
            {
                **base(c.name, c.created_at),
                "TypeName": ctype.name if ctype else None,
                "Space": space.name if space else None,
                "Description": c.description or c.name,
                **ext("Component", c.id),
                "SerialNumber": c.serial_number,
                "InstallationDate": _day(c.installation_date),
                "WarrantyStartDate": _day(c.warranty_start_date or c.installation_date),
                "TagNumber": c.tag_number,
                "BarCode": c.bar_code,
                "AssetIdentifier": c.asset_identifier,
            }
        )
    for sy in reg.systems:
        members: list[str | None] = [
            *sorted(component_by_id[i].name for i in reg.members.get(sy.id, []) if i in component_by_id)
        ]
        for component_name in members or [None]:
            out["System"].append(
                {
                    **base(sy.name, sy.created_at),
                    "Category": sy.category,
                    "ComponentNames": component_name,
                    **ext("System", sy.id),
                    "Description": sy.description or sy.name,
                }
            )
    for d in reg.documents:
        owner: Any = (component_by_id if d.entity_type == ENTITY_COMPONENT else type_by_id).get(d.entity_id or 0)
        out["Document"].append(
            {
                **base(d.name, d.created_at),
                "Category": d.category,
                "ApprovalBy": "Information Only",
                "Stage": "As Built",
                "SheetName": "Component" if d.entity_type == ENTITY_COMPONENT else "Type",
                "RowName": owner.name if owner else None,
                "Directory": "documents",
                "File": d.name,
                **ext("File", d.id),
                "Description": d.name,
                "Reference": f"rev {d.revision}",
            }
        )
    for sheet, items in (("Type", reg.types), ("Component", reg.components)):
        for item in items:
            for key, value in sorted(item.attributes.items()):
                out["Attribute"].append(
                    {
                        **base(key, item.created_at),
                        "Category": "Submitted",
                        "SheetName": sheet,
                        "RowName": item.name,
                        "Value": value,
                        "Unit": None,
                        **ext("Attribute", item.id),
                        "Description": key,
                    }
                )
    return out


def workbook(rows: dict[str, list[dict[str, Any]]]) -> bytes:
    book = Workbook()
    first = book.active
    assert first is not None
    book.remove(first)
    for name, headers in SHEETS.items():
        sheet = book.create_sheet(name)
        sheet.append(headers)
        for cell, header in zip(sheet[1], headers, strict=True):
            cell.font = Font(bold=True)
            cell.fill = _fill(header)
        widths = [len(h) for h in headers]
        for row in rows[name]:
            values = [row.get(h) for h in headers]
            sheet.append(values)
            widths = [max(w, min(50, len(str(v)) if v is not None else 0)) for w, v in zip(widths, values, strict=True)]
        for i, w in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(i)].width = w + 2
        sheet.freeze_panes = "B2"
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def validate(reg: Register) -> CobieReport:
    issues: dict[str, list[CobieIssue]] = {name: [] for name in SHEETS}

    def err(sheet: str, row: str | None, fld: str | None, message: str) -> None:
        issues[sheet].append(CobieIssue(severity="error", row=row, field=fld, message=message))

    def warn(sheet: str, row: str | None, fld: str | None, message: str) -> None:
        issues[sheet].append(CobieIssue(severity="warning", row=row, field=fld, message=message))

    def duplicates(sheet: str, names: list[str]) -> None:
        for name, n in Counter(n.strip().lower() for n in names).items():
            if n > 1:
                original = next(x for x in names if x.strip().lower() == name)
                err(sheet, original, "Name", f"{n} rows are named '{original}'; names must be unique")

    def missing(sheet: str, name: str, fld: str, value: Any, *, error: bool = True) -> None:
        if value in (None, "", []):
            (err if error else warn)(sheet, name, fld, f"{fld} is empty")

    if not reg.facilities:
        err("Facility", None, None, "Add a facility")
    for f in reg.facilities:
        missing("Facility", f.name, "Category", f.category)
    duplicates("Facility", [f.name for f in reg.facilities])

    if not reg.floors:
        err("Floor", None, None, "Add at least one floor")
    for fl in reg.floors:
        missing("Floor", fl.name, "Category", fl.category)
    duplicates("Floor", [f.name for f in reg.floors])

    for s in reg.spaces:
        missing("Space", s.name, "Category", s.category)
        missing("Space", s.name, "GrossArea", s.gross_area, error=False)
    duplicates("Space", [s.name for s in reg.spaces])

    for z in reg.zones:
        missing("Zone", z.name, "Category", z.category)
        missing("Zone", z.name, "SpaceNames", z.space_ids)
    duplicates("Zone", [z.name for z in reg.zones])

    used_types = {c.type_id for c in reg.components}
    for t in reg.types:
        missing("Type", t.name, "Category", t.category)
        missing("Type", t.name, "Manufacturer", t.manufacturer_id)
        missing("Type", t.name, "ModelNumber", t.model_number)
        missing("Type", t.name, "WarrantyDurationParts", t.warranty_duration_parts, error=False)
        missing("Type", t.name, "ReplacementCost", t.replacement_cost, error=False)
        missing("Type", t.name, "ExpectedLife", t.expected_life, error=False)
        if t.id not in used_types:
            warn("Type", t.name, None, "No component uses this type")
    duplicates("Type", [t.name for t in reg.types])

    for c in reg.components:
        missing("Component", c.name, "TypeName", c.type_id)
        missing("Component", c.name, "Space", c.space_id)
        missing("Component", c.name, "SerialNumber", c.serial_number, error=False)
        missing("Component", c.name, "InstallationDate", c.installation_date, error=False)
    duplicates("Component", [c.name for c in reg.components])

    for sy in reg.systems:
        missing("System", sy.name, "Category", sy.category)
        missing("System", sy.name, "ComponentNames", reg.members.get(sy.id))
    duplicates("System", [s.name for s in reg.systems])

    referenced = {i for t in reg.types for i in (t.manufacturer_id, t.warranty_guarantor_id) if i}
    for cid, person in reg.contacts.items():
        label = f"{person.first_name} {person.last_name}".strip()
        if not person.email:
            (err if cid in referenced else warn)("Contact", label, "Email", "No email address; COBie keys contacts by email")
        if not person.company_id:
            warn("Contact", label, "Company", "No company")
    duplicates("Contact", [c.email for c in reg.contacts.values() if c.email])

    counts = {name: len(rows) for name, rows in build_rows(reg, "validation@example.com").items()}
    counts["Contact"] = len(reg.contacts)
    sheets = [CobieSheetReport(sheet=name, rows=counts[name], issues=issues[name]) for name in SHEETS]
    errors = sum(1 for s in sheets for i in s.issues if i.severity == "error")
    warnings = sum(1 for s in sheets for i in s.issues if i.severity == "warning")
    return CobieReport(valid=errors == 0, errors=errors, warnings=warnings, sheets=sheets)
