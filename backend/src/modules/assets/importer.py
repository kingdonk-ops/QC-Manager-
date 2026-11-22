"""Bulk import of components or product types from CSV or Excel, with column mapping.

A row is a duplicate when a row of the same kind with the same name (any case) is already in the
project. ``on_duplicate`` decides: ``skip`` leaves it, ``update`` fills in the row's non-empty values.
For components, the type and space columns hold names: an unknown type is created, an unknown space is
reported. Columns not mapped to a field become attributes when ``extra_as_attributes`` is set.
A dry run reports what would happen and writes nothing.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..contacts.models import Company, Contact
from .constants import AssetKind, ComponentStatus
from .models import AssetComponent, AssetSpace, AssetType
from .schemas import AssetImportReport, ImportTarget
from .service import existing_names

COMPONENT_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("name", "tag", "asset", "asset name", "component", "component name", "asset tag"),
    "description": ("description", "desc"),
    "type": ("type", "typename", "type name", "product type", "asset type"),
    "space": ("space", "room", "location", "space name", "room name"),
    "serial_number": ("serial", "serial number", "serial no", "s n"),
    "installation_date": ("installation date", "installed", "install date", "installed on"),
    "warranty_start_date": ("warranty start", "warranty start date", "warranty from"),
    "tag_number": ("tag number", "tag no"),
    "bar_code": ("barcode", "bar code", "qr", "qr code"),
    "asset_identifier": ("asset identifier", "asset id", "asset number", "asset no"),
    "status": ("status", "state"),
}

TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("name", "type", "type name", "product", "product type"),
    "description": ("description", "desc"),
    "category": ("category", "classification", "uniclass", "omniclass", "code"),
    "asset_kind": ("asset type", "assettype", "fixed moveable"),
    "manufacturer": ("manufacturer", "make", "brand", "supplier"),
    "model_number": ("model", "model number", "model no"),
    "warranty_guarantor": ("warranty guarantor", "guarantor", "warranty guarantor parts"),
    "warranty_duration_parts": ("warranty duration parts", "warranty parts", "warranty", "warranty years"),
    "warranty_duration_labor": ("warranty duration labor", "warranty labour", "warranty labor"),
    "warranty_duration_unit": ("warranty duration unit", "warranty unit"),
    "replacement_cost": ("replacement cost", "cost", "price"),
    "expected_life": ("expected life", "life", "life expectancy", "service life"),
    "duration_unit": ("duration unit", "life unit"),
    "nominal_length": ("nominal length", "length"),
    "nominal_width": ("nominal width", "width"),
    "nominal_height": ("nominal height", "height"),
    "material": ("material",),
    "color": ("color", "colour"),
}

FIELDS: dict[str, dict[str, tuple[str, ...]]] = {"components": COMPONENT_FIELDS, "types": TYPE_FIELDS}
NUMBERS = {
    "warranty_duration_parts",
    "warranty_duration_labor",
    "expected_life",
    "nominal_length",
    "nominal_width",
    "nominal_height",
}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", header.lower()).strip()


def auto_mapping(target: ImportTarget, columns: list[str]) -> dict[str, str]:
    """Guess ``{field: column}`` from the headers; each column is used once."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for field, aliases in FIELDS[target].items():
        known = {_norm(a) for a in aliases} | {_norm(field)}
        for column in columns:
            if column not in used and _norm(column) in known:
                mapping[field] = column
                used.add(column)
                break
    return mapping


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{text}' isn't a date")


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise ValueError(f"'{value}' isn't a number") from exc


def _money(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' isn't an amount") from exc


async def _contact(db: AsyncSession, text: str, cache: dict[str, int | None]) -> int | None:
    """A contact by email, by name, or the first contact of a company of that name."""
    if not text:
        return None
    key = text.lower()
    if key not in cache:
        found = await db.scalar(
            select(Contact.id)
            .outerjoin(Company, Company.id == Contact.company_id)
            .where(
                or_(
                    func.lower(Contact.email) == key,
                    func.lower(Contact.first_name + " " + Contact.last_name) == key,
                    func.lower(Company.name) == key,
                )
            )
            .order_by(Contact.id)
            .limit(1)
        )
        cache[key] = found
    return cache[key]


async def run_import(
    db: AsyncSession,
    project_id: int,
    target: ImportTarget,
    columns: list[str],
    rows: list[dict[str, Any]],
    mapping: dict[str, str] | None,
    *,
    on_duplicate: Literal["skip", "update"],
    dry_run: bool,
    extra_as_attributes: bool,
) -> AssetImportReport:
    mapping = mapping or auto_mapping(target, columns)
    report = AssetImportReport(target=target, dry_run=dry_run, rows=len(rows), created=0, updated=0, skipped=0)
    unknown = [c for c in mapping.values() if c not in columns]
    if unknown:
        report.errors.append(f"Columns not in the file: {', '.join(unknown)}")
        return report
    if "name" not in mapping:
        report.errors.append("Map a column to the name.")
        return report
    extra_columns = [c for c in columns if c not in mapping.values()] if extra_as_attributes else []
    model: Any = AssetComponent if target == "components" else AssetType
    existing = await existing_names(db, model, project_id)
    types = await existing_names(db, AssetType, project_id) if target == "components" else {}
    spaces = await existing_names(db, AssetSpace, project_id) if target == "components" else {}
    contacts: dict[str, int | None] = {}
    seen: set[str] = set()

    for line, row in enumerate(rows, start=2):
        value = {field: row.get(column) for field, column in mapping.items()}
        name = _text(value.get("name"))
        if not name:
            report.errors.append(f"Row {line}: no name")
            report.skipped += 1
            continue
        if name.lower() in seen:
            report.duplicates.append(f"Row {line}: {name} (repeated in the file)")
            report.skipped += 1
            continue
        seen.add(name.lower())
        try:
            if target == "components":
                fields = await _component_fields(db, project_id, value, types, spaces, dry_run, line, report)
            else:
                fields = await _type_fields(db, value, contacts, line, report)
        except ValueError as exc:
            report.errors.append(f"Row {line}: {exc}")
            report.skipped += 1
            continue
        attributes = {c: _text(row.get(c)) for c in extra_columns if _text(row.get(c))}
        current = existing.get(name.lower())
        if current is not None:
            report.duplicates.append(f"Row {line}: {name}")
            if on_duplicate == "skip":
                report.skipped += 1
                continue
            report.updated += 1
            if not dry_run:
                for key, v in fields.items():
                    if v not in (None, ""):
                        setattr(current, key, v)
                if attributes:
                    current.attributes = {**current.attributes, **attributes}
            continue
        report.created += 1
        if not dry_run:
            fields = {k: v for k, v in fields.items() if v not in (None, "")}
            new = model(project_id=project_id, name=name, attributes=attributes, **fields)
            db.add(new)
            existing[name.lower()] = new

    if not dry_run:
        await db.commit()
    return report


async def _component_fields(
    db: AsyncSession,
    project_id: int,
    value: dict[str, Any],
    types: dict[str, Any],
    spaces: dict[str, Any],
    dry_run: bool,
    line: int,
    report: AssetImportReport,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "description": _text(value.get("description")) or None,
        "serial_number": _text(value.get("serial_number")) or None,
        "tag_number": _text(value.get("tag_number")) or None,
        "bar_code": _text(value.get("bar_code")) or None,
        "asset_identifier": _text(value.get("asset_identifier")) or None,
        "installation_date": _date(value.get("installation_date")),
        "warranty_start_date": _date(value.get("warranty_start_date")),
    }
    status = _text(value.get("status")).lower().replace(" ", "_").replace("-", "_")
    if status:
        if status not in ComponentStatus._value2member_map_:
            raise ValueError(f"'{status}' isn't a status")
        fields["status"] = status
    type_name = _text(value.get("type"))
    if type_name:
        found = types.get(type_name.lower())
        if found is None and not dry_run:
            found = AssetType(project_id=project_id, name=type_name)
            db.add(found)
            await db.flush()
            types[type_name.lower()] = found
        fields["type_id"] = found.id if found is not None else None
    space_name = _text(value.get("space"))
    if space_name:
        space = spaces.get(space_name.lower())
        if space is None:
            report.errors.append(f"Row {line}: no space named '{space_name}'; imported without a space")
        else:
            fields["space_id"] = space.id
    return fields


async def _type_fields(
    db: AsyncSession, value: dict[str, Any], contacts: dict[str, int | None], line: int, report: AssetImportReport
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        key: _text(value.get(key)) or None for key in ("description", "category", "model_number", "material", "color")
    }
    for key in NUMBERS:
        fields[key] = _number(value.get(key))
    fields["replacement_cost"] = _money(value.get("replacement_cost"))
    for key in ("warranty_duration_unit", "duration_unit"):
        unit = _text(value.get(key)).lower()
        fields[key] = unit or None
    kind = _text(value.get("asset_kind")).lower()
    if kind:
        fields["asset_kind"] = AssetKind.MOVEABLE.value if kind.startswith("move") else AssetKind.FIXED.value
    for field, column in (("manufacturer", "manufacturer_id"), ("warranty_guarantor", "warranty_guarantor_id")):
        text = _text(value.get(field))
        if text:
            contact_id = await _contact(db, text, contacts)
            if contact_id is None:
                report.errors.append(f"Row {line}: no contact or company '{text}' in Contacts; {field} left blank")
            fields[column] = contact_id
    return fields
