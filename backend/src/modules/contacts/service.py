from collections import defaultdict
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ResourceNotFoundError
from ..projects.models import Project
from .models import Company, Contact, ProjectContact
from .schemas import CompanyRead, ContactRead, ProjectRole


class ContactNotFoundError(ResourceNotFoundError):
    public_detail = "Contact not found."


class CompanyNotFoundError(ResourceNotFoundError):
    public_detail = "Company not found."


def full_name(c: Contact) -> str:
    return f"{c.first_name} {c.last_name}".strip()


async def contact_names(db: AsyncSession, ids: set[int] | list[int]) -> dict[int, str]:
    """``{contact_id: "Name (Company)"}`` for other modules' lists."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = await db.execute(
        select(Contact.id, Contact.first_name, Contact.last_name, Company.name)
        .outerjoin(Company, Company.id == Contact.company_id)
        .where(Contact.id.in_(ids))
    )
    return {cid: f"{first} {last}".strip() + (f" ({co})" if co else "") for cid, first, last, co in rows.all()}


async def contact_emails(db: AsyncSession, ids: list[int]) -> dict[int, str]:
    rows = await db.execute(select(Contact.id, Contact.email).where(Contact.id.in_(ids), Contact.email.is_not(None)))
    return {cid: email for cid, email in rows.all()}


async def read_contacts(db: AsyncSession, contacts: list[Contact]) -> list[dict[str, Any]]:
    ids = [c.id for c in contacts]
    companies = {c.company_id for c in contacts if c.company_id}
    names = (
        dict((await db.execute(select(Company.id, Company.name).where(Company.id.in_(companies)))).tuples().all())
        if companies
        else {}
    )
    roles: dict[int, list[ProjectRole]] = defaultdict(list)
    if ids:
        rows = await db.execute(
            select(ProjectContact.contact_id, Project.id, Project.code, Project.name, ProjectContact.role)
            .join(Project, Project.id == ProjectContact.project_id)
            .where(ProjectContact.contact_id.in_(ids))
            .order_by(Project.code)
        )
        for cid, pid, code, pname, role in rows.all():
            roles[cid].append(ProjectRole(project_id=pid, project_code=code, project_name=pname, role=role))
    return [
        ContactRead.model_validate(c)
        .model_copy(
            update={
                "full_name": full_name(c),
                "company_name": names.get(c.company_id) if c.company_id else None,
                "projects": roles[c.id],
            }
        )
        .model_dump(mode="json")
        for c in contacts
    ]


def _contact_filters(
    search: str | None, type_: str | None, company_id: int | None, project_id: int | None, tag: str | None
) -> list[Any]:
    filters: list[Any] = []
    if search:
        like = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(Contact.first_name + " " + Contact.last_name).like(like),
                func.lower(func.coalesce(Contact.email, "")).like(like),
                func.lower(func.coalesce(Contact.job_title, "")).like(like),
                Contact.company_id.in_(select(Company.id).where(func.lower(Company.name).like(like))),
            )
        )
    if type_:
        filters.append(Contact.type == type_)
    if company_id:
        filters.append(Contact.company_id == company_id)
    if project_id:
        filters.append(Contact.id.in_(select(ProjectContact.contact_id).where(ProjectContact.project_id == project_id)))
    if tag:
        filters.append(func.lower(cast(Contact.tags, String)).like(f'%"{tag.lower()}"%'))
    return filters


async def page(db: AsyncSession, *, skip: int, limit: int, **filters: Any) -> dict[str, Any]:
    where = _contact_filters(**filters)
    total = await db.scalar(select(func.count()).select_from(Contact).where(*where))
    rows = (
        await db.execute(
            select(Contact).where(*where).order_by(Contact.last_name, Contact.first_name).offset(skip).limit(limit)
        )
    ).scalars()
    return {"data": await read_contacts(db, list(rows)), "total_count": total or 0}


async def get_contact(db: AsyncSession, contact_id: int) -> Contact:
    c = await db.get(Contact, contact_id)
    if c is None:
        raise ContactNotFoundError("No such contact")
    return c


async def get_company(db: AsyncSession, company_id: int) -> Company:
    c = await db.get(Company, company_id)
    if c is None:
        raise CompanyNotFoundError("No such company")
    return c


async def companies_page(db: AsyncSession, *, skip: int, limit: int, search: str | None) -> dict[str, Any]:
    where = [func.lower(Company.name).like(f"%{search.lower()}%")] if search else []
    total = await db.scalar(select(func.count()).select_from(Company).where(*where))
    counts = select(Contact.company_id, func.count().label("n")).group_by(Contact.company_id).subquery()
    rows = (
        await db.execute(
            select(Company, counts.c.n)
            .outerjoin(counts, counts.c.company_id == Company.id)
            .where(*where)
            .order_by(Company.name)
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return {
        "data": [
            CompanyRead.model_validate(c).model_copy(update={"contact_count": n or 0}).model_dump(mode="json") for c, n in rows
        ],
        "total_count": total or 0,
    }
