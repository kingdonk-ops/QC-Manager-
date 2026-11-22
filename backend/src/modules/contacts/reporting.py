"""Contacts for reporting: the directory and companies as datasets, and the import hub's contacts importer
(which hands over to ``importer.run_import``)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import (
    Column,
    Dataset,
    Importer,
    ImportField,
    ImportJob,
    ImportReport,
    register_dataset,
    register_importer,
)
from .importer import ALIASES, FIELDS, run_import
from .models import Company, Contact, ProjectContact


async def contact_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    query = (
        select(Contact, Company.name)
        .outerjoin(Company, Company.id == Contact.company_id)
        .order_by(Contact.last_name, Contact.first_name)
    )
    roles: dict[int, str | None] = {}
    if project_id is not None:
        links = (
            await db.execute(
                select(ProjectContact.contact_id, ProjectContact.role).where(ProjectContact.project_id == project_id)
            )
        ).all()
        roles = {cid: role for cid, role in links}
        query = query.where(Contact.id.in_(roles))
    return [
        {
            "name": f"{c.first_name} {c.last_name}".strip(),
            "first_name": c.first_name,
            "last_name": c.last_name,
            "company": company,
            "type": c.type,
            "job_title": c.job_title,
            "email": c.email,
            "phone": c.phone,
            "mobile": c.mobile,
            "tags": c.tags,
            "project_role": roles.get(c.id),
            "contacts": 1,
        }
        for c, company in (await db.execute(query)).all()
    ]


async def company_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    counts = (
        select(Contact.company_id, func.count().label("n")).where(Contact.company_id.is_not(None)).group_by(Contact.company_id)
    ).subquery()
    rows = await db.execute(
        select(Company, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.company_id == Company.id)
        .order_by(Company.name)
    )
    return [
        {"name": co.name, "type": co.type, "email": co.email, "phone": co.phone, "website": co.website, "contacts": n}
        for co, n in rows.all()
    ]


register_dataset(
    Dataset(
        name="contacts",
        module="contacts",
        title="Contacts",
        description="The contacts directory; with a project, only the project's contacts and their roles.",
        project_scoped=False,
        permission="contacts.read",
        columns=[
            Column("name", "Name"),
            Column("first_name", "First name"),
            Column("last_name", "Last name"),
            Column("company", "Company"),
            Column("type", "Type"),
            Column("job_title", "Job title"),
            Column("email", "Email"),
            Column("phone", "Phone"),
            Column("mobile", "Mobile"),
            Column("tags", "Tags"),
            Column("project_role", "Project role"),
            Column("contacts", "Count", "number"),
        ],
        rows=contact_rows,
    )
)

register_dataset(
    Dataset(
        name="companies",
        module="contacts",
        title="Companies",
        description="Companies in the contacts directory with their number of contacts.",
        project_scoped=False,
        permission="contacts.read",
        columns=[
            Column("name", "Company"),
            Column("type", "Type"),
            Column("email", "Email"),
            Column("phone", "Phone"),
            Column("website", "Website"),
            Column("contacts", "Contacts", "number"),
        ],
        rows=company_rows,
    )
)


async def import_contacts(db: AsyncSession, job: ImportJob) -> ImportReport:
    result = await run_import(
        db,
        job.columns,
        job.raw_rows,
        job.mapping or None,
        on_duplicate="skip" if job.options.get("on_duplicate") == "skip" else "update",
        dry_run=job.dry_run,
        project_id=job.project_id,
        project_role=job.options.get("project_role") or None,
    )
    return ImportReport(
        dry_run=result.dry_run,
        rows=result.rows,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        errors=result.errors,
        warnings=[f"Duplicate: {d}" for d in result.duplicates],
    )


register_importer(
    Importer(
        name="contacts",
        module="contacts",
        title="Contacts",
        description="People and their companies; matched to existing contacts by email, or by name and company.",
        project_scoped=False,
        permission="contacts.import",
        options={"on_duplicate": ["update", "skip"]},
        fields=[ImportField(f, f.replace("_", " ").capitalize(), aliases=ALIASES.get(f, ()), required=False) for f in FIELDS],
        apply=import_contacts,
    )
)
