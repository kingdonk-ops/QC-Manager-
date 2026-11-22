"""Bulk contacts import from CSV or Excel, with column mapping and duplicate handling.

A row is a duplicate when its email matches an existing contact, or, with no email, when its first
name, last name and company all match. ``on_duplicate`` decides: ``skip`` leaves the existing contact,
``update`` fills in the row's non-empty values. A dry run reports what would happen and writes nothing.
"""

import re
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import ContactType
from .models import Company, Contact, ProjectContact
from .schemas import ImportReport

FIELDS = ("first_name", "last_name", "full_name", "email", "phone", "mobile", "job_title", "company", "type", "tags", "notes")

ALIASES: dict[str, tuple[str, ...]] = {
    "first_name": ("first name", "firstname", "given name", "forename"),
    "last_name": ("last name", "lastname", "surname", "family name"),
    "full_name": ("name", "full name", "contact", "contact name"),
    "email": ("email", "e-mail", "email address", "mail"),
    "phone": ("phone", "telephone", "work phone", "office"),
    "mobile": ("mobile", "cell", "mobile phone"),
    "job_title": ("title", "job title", "position", "role"),
    "company": ("company", "organisation", "organization", "firm", "employer"),
    "type": ("type", "category", "contact type"),
    "tags": ("tags", "labels"),
    "notes": ("notes", "comments", "remarks"),
}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z]+", " ", header.lower()).strip()


def auto_mapping(columns: list[str]) -> dict[str, str]:
    """Guess ``{field: column}`` from the headers."""
    mapping: dict[str, str] = {}
    for field, aliases in ALIASES.items():
        known = {_norm(a) for a in aliases} | {field.replace("_", " ")}
        for column in columns:
            if _norm(column) in known:
                mapping.setdefault(field, column)
                break
    return mapping


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


async def run_import(
    db: AsyncSession,
    columns: list[str],
    rows: list[dict[str, Any]],
    mapping: dict[str, str] | None,
    *,
    on_duplicate: Literal["skip", "update"],
    dry_run: bool,
    project_id: int | None,
    project_role: str | None,
) -> ImportReport:
    mapping = mapping or auto_mapping(columns)
    report = ImportReport(dry_run=dry_run, rows=len(rows), created=0, updated=0, skipped=0, columns=columns)
    unknown = [c for c in mapping.values() if c not in columns]
    if unknown:
        report.errors.append(f"Columns not in the file: {', '.join(unknown)}")
        return report
    companies = {name.lower(): cid for cid, name in (await db.execute(select(Company.id, Company.name))).all()}

    for line, row in enumerate(rows, start=2):
        value = {field: _text(row.get(column)) for field, column in mapping.items()}
        first, last = value.get("first_name", ""), value.get("last_name", "")
        if not first and value.get("full_name"):
            first, _, last = value["full_name"].partition(" ")
        if not first:
            report.errors.append(f"Row {line}: no name")
            report.skipped += 1
            continue
        email = value.get("email", "").lower() or None
        if email and "@" not in email:
            report.errors.append(f"Row {line}: '{email}' isn't an email address")
            email = None
        company_name = value.get("company", "")
        company_id = companies.get(company_name.lower()) if company_name else None
        if company_name and company_id is None and not dry_run:
            company = Company(name=company_name)
            db.add(company)
            await db.flush()
            company_id = companies[company_name.lower()] = company.id

        if email:
            existing = await db.scalar(select(Contact).where(func.lower(Contact.email) == email))
        else:
            existing = await db.scalar(
                select(Contact).where(
                    func.lower(Contact.first_name) == first.lower(),
                    func.lower(Contact.last_name) == last.lower(),
                    Contact.company_id.is_(company_id) if company_id is None else Contact.company_id == company_id,
                )
            )
        kind = value.get("type", "").lower()
        fields: dict[str, Any] = {
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": value.get("phone") or None,
            "mobile": value.get("mobile") or None,
            "job_title": value.get("job_title") or None,
            "company_id": company_id,
            "type": kind if kind in ContactType._value2member_map_ else None,
            "tags": [t.strip() for t in value.get("tags", "").split(",") if t.strip()] or None,
            "notes": value.get("notes") or None,
        }
        if existing is not None:
            report.duplicates.append(f"Row {line}: {first} {last}".strip() + (f" <{email}>" if email else ""))
            if on_duplicate == "skip":
                report.skipped += 1
                target = existing
            else:
                report.updated += 1
                if not dry_run:
                    for key, v in fields.items():
                        if v:
                            setattr(existing, key, v)
                target = existing
        else:
            report.created += 1
            if dry_run:
                continue
            target = Contact(**{k: v for k, v in fields.items() if v is not None})
            db.add(target)
            await db.flush()
        if project_id and not dry_run and await db.get(ProjectContact, (project_id, target.id)) is None:
            db.add(ProjectContact(project_id=project_id, contact_id=target.id, role=project_role))

    if not dry_run:
        await db.commit()
    return report
