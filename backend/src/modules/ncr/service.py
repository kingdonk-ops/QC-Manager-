from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import assert_transition, history_of, next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError
from ..contacts.models import Company
from ..contacts.service import contact_names
from ..notifications.constants import Category
from ..notifications.service import notify
from ..projects.models import Project
from ..user.models import User
from .constants import FLOW, ActionStatus, NcrStatus
from .models import Ncr, NcrAction
from .schemas import NcrActionRead, NcrRead

ENTITY = "ncr"
OPEN_ACTION = (ActionStatus.OPEN.value, ActionStatus.IN_PROGRESS.value)


class NcrNotFoundError(ResourceNotFoundError):
    public_detail = "NCR not found."


class NcrActionNotFoundError(ResourceNotFoundError):
    public_detail = "Action not found."


def link_of(ncr: Ncr) -> str:
    return f"/ncr?project={ncr.project_id}&id={ncr.id}"


def total_cost(ncr: Ncr) -> Decimal:
    return Decimal(ncr.rework_cost or 0) + Decimal(ncr.delay_cost or 0) + Decimal(ncr.other_cost or 0)


async def user_names(db: AsyncSession, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(wanted)))).tuples().all())


async def get_ncr(db: AsyncSession, ncr_id: int) -> Ncr:
    ncr = await db.get(Ncr, ncr_id)
    if ncr is None:
        raise NcrNotFoundError("No such NCR")
    return ncr


async def get_action(db: AsyncSession, ncr: Ncr, action_id: int) -> NcrAction:
    action = await db.get(NcrAction, action_id)
    if action is None or action.ncr_id != ncr.id:
        raise NcrActionNotFoundError("No such action")
    return action


async def read_ncrs(db: AsyncSession, ncrs: list[Ncr], *, with_actions: bool = False) -> list[dict[str, Any]]:
    ids = [n.id for n in ncrs]
    actions: list[NcrAction] = []
    if ids:
        actions = list(
            (
                await db.execute(select(NcrAction).where(NcrAction.ncr_id.in_(ids)).order_by(NcrAction.due_date, NcrAction.id))
            ).scalars()
        )
    people = await user_names(
        db,
        {n.raised_by_id for n in ncrs}
        | {n.responsible_user_id for n in ncrs}
        | {a.responsible_id for a in actions}
        | {a.verified_by_id for a in actions},
    )
    contacts = await contact_names(db, {n.responsible_contact_id for n in ncrs if n.responsible_contact_id})
    company_ids = {n.responsible_company_id for n in ncrs if n.responsible_company_id}
    companies = (
        dict((await db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids)))).tuples().all())
        if company_ids
        else {}
    )
    today = date.today()
    by_ncr: dict[int, list[NcrActionRead]] = {i: [] for i in ids}
    for a in actions:
        by_ncr[a.ncr_id].append(
            NcrActionRead.model_validate(a).model_copy(
                update={
                    "responsible_name": people.get(a.responsible_id) if a.responsible_id else None,
                    "verified_by_name": people.get(a.verified_by_id) if a.verified_by_id else None,
                    "overdue": bool(a.due_date and a.due_date < today and a.status in OPEN_ACTION),
                }
            )
        )
    out = []
    for n in ncrs:
        mine = by_ncr.get(n.id, [])
        out.append(
            NcrRead.model_validate(n)
            .model_copy(
                update={
                    "raised_by_name": people.get(n.raised_by_id) if n.raised_by_id else None,
                    "responsible_user_name": people.get(n.responsible_user_id) if n.responsible_user_id else None,
                    "responsible_contact_name": contacts.get(n.responsible_contact_id) if n.responsible_contact_id else None,
                    "responsible_company_name": (companies.get(n.responsible_company_id) if n.responsible_company_id else None),
                    "total_cost": total_cost(n),
                    "open_actions": sum(1 for a in mine if a.status in OPEN_ACTION),
                    "actions": mine if with_actions else [],
                }
            )
            .model_dump(mode="json")
        )
    return out


def filters(
    project_id: int,
    status: str | None = None,
    severity: str | None = None,
    source: str | None = None,
    trade: str | None = None,
    open_only: bool = False,
    search: str | None = None,
) -> list[Any]:
    where: list[Any] = [Ncr.project_id == project_id]
    if status:
        where.append(Ncr.status == status)
    if severity:
        where.append(Ncr.severity == severity)
    if source:
        where.append(Ncr.source == source)
    if trade:
        where.append(func.lower(Ncr.trade) == trade.lower())
    if open_only:
        where.append(Ncr.status != NcrStatus.CLOSED.value)
    if search:
        like = f"%{search.lower()}%"
        where.append(
            or_(
                func.lower(Ncr.title + " " + Ncr.code).like(like),
                func.lower(func.coalesce(Ncr.location, "")).like(like),
                func.lower(func.coalesce(Ncr.description, "")).like(like),
            )
        )
    return where


async def create_ncr(
    db: AsyncSession, *, project_id: int, title: str, raised_by_id: int | None, commit: bool = True, **fields: Any
) -> Ncr:
    """Raise an NCR, notify the responsible user, and (by default) commit. For other modules too."""
    values = {k: (v.value if hasattr(v, "value") else v) for k, v in fields.items() if v is not None}
    values.setdefault("raised_on", date.today())
    ncr = Ncr(
        project_id=project_id,
        code=await next_reference(db, "NCR", project_id),
        title=title[:300],
        raised_by_id=raised_by_id,
        status=NcrStatus.OPEN.value,
        **values,
    )
    db.add(ncr)
    await db.flush()
    await record_transition(db, ENTITY, ncr.id, None, ncr.status, raised_by_id, note="Raised")
    await notify_responsible(db, ncr, raised_by_id)
    if commit:
        await db.commit()
    return ncr


async def notify_responsible(db: AsyncSession, ncr: Ncr, actor_id: int | None) -> None:
    if ncr.responsible_user_id:
        await notify(
            db,
            [ncr.responsible_user_id],
            Category.ASSIGNMENT,
            f"{ncr.code}: {ncr.title}",
            body=f"A {ncr.severity} non-conformance is assigned to you.",
            link=link_of(ncr),
            entity=(ENTITY, ncr.id),
            actor_id=actor_id,
        )


async def change_status(db: AsyncSession, ncr: Ncr, target: str, note: str | None, actor_id: int) -> None:
    assert_transition(FLOW, ncr.status, target)
    before = ncr.status
    ncr.status = target
    ncr.closed_at = datetime.now(UTC) if target == NcrStatus.CLOSED else None
    if before == NcrStatus.VERIFIED and target == NcrStatus.CORRECTIVE_ACTION_PLANNED and not note:
        note = "Verification failed"
    await record_transition(db, ENTITY, ncr.id, before, target, actor_id, note)
    watchers = {ncr.raised_by_id, ncr.responsible_user_id} - {None, actor_id}
    await notify(
        db,
        [w for w in watchers if w],
        Category.STATUS,
        f"{ncr.code} is now {target.replace('_', ' ')}",
        body=note or ncr.title,
        link=link_of(ncr),
        entity=(ENTITY, ncr.id),
        actor_id=actor_id,
    )
    await db.commit()


async def notify_action(db: AsyncSession, ncr: Ncr, action: NcrAction, actor_id: int) -> None:
    if action.responsible_id and action.responsible_id != actor_id:
        await notify(
            db,
            [action.responsible_id],
            Category.ASSIGNMENT,
            f"{ncr.code}: {action.kind} action",
            body=action.description[:300] + (f" (due {action.due_date.isoformat()})" if action.due_date else ""),
            link=link_of(ncr),
            entity=(ENTITY, ncr.id),
            actor_id=actor_id,
        )


async def update_action(db: AsyncSession, ncr: Ncr, action: NcrAction, changes: dict[str, Any], actor_id: int) -> None:
    before_responsible, before_status = action.responsible_id, action.status
    for key, value in changes.items():
        setattr(action, key, value.value if hasattr(value, "value") else value)
    if action.status != before_status:
        now = datetime.now(UTC)
        if action.status in (ActionStatus.DONE, ActionStatus.VERIFIED) and action.completed_at is None:
            action.completed_at = now
        if action.status == ActionStatus.VERIFIED:
            action.verified_by_id, action.verified_at = actor_id, now
        elif before_status == ActionStatus.VERIFIED:
            action.verified_by_id, action.verified_at = None, None
        if action.status in OPEN_ACTION:
            action.completed_at = None
    if action.responsible_id and action.responsible_id != before_responsible:
        await notify_action(db, ncr, action, actor_id)
    await db.commit()


async def history(db: AsyncSession, ncr: Ncr) -> list[dict[str, Any]]:
    rows = await history_of(db, ENTITY, ncr.id)
    names = await user_names(db, {r["changed_by_id"] for r in rows})
    return [{**r, "changed_by_name": names.get(r["changed_by_id"]) if r["changed_by_id"] else None} for r in rows]


def label(value: str | None) -> str:
    return (value or "").replace("_", " ").capitalize()


async def report_pdf(db: AsyncSession, ncr: Ncr) -> bytes:
    read = (await read_ncrs(db, [ncr], with_actions=True))[0]
    project = await db.get(Project, ncr.project_id)
    doc = Document(
        title=f"Non-Conformance Report {ncr.code}",
        subtitle=f"{ncr.title} · {project.code if project else ''} {project.name if project else ''}".strip(),
        footer=f"{ncr.code}",
    )
    responsible = read["responsible_user_name"] or read["responsible_contact_name"] or read["responsible_company_name"] or "-"
    doc.fields(
        [
            ("Status", label(ncr.status)),
            ("Severity", label(ncr.severity)),
            ("Raised by", read["raised_by_name"] or "-"),
            ("Date raised", ncr.raised_on.isoformat() if ncr.raised_on else "-"),
            ("Location", ncr.location or "-"),
            ("Trade", ncr.trade or "-"),
            ("Responsible party", responsible),
            ("Source", label(ncr.source) + (f" ({ncr.source_reference})" if ncr.source_reference else "")),
            ("Spec / drawing ref.", ncr.spec_reference or "-"),
        ]
    )
    doc.heading("Description of non-conformance")
    doc.paragraph(ncr.description or "-")
    doc.heading("Root cause")
    doc.fields([("Category", label(ncr.root_cause_category) or "-")])
    doc.paragraph(ncr.root_cause_description or "-")
    doc.heading("Disposition")
    pairs: list[tuple[str, Any]] = [("Disposition", label(ncr.disposition) or "-")]
    if ncr.concession_reference:
        pairs.append(("Concession ref.", ncr.concession_reference))
    doc.fields(pairs)
    if ncr.disposition_notes:
        doc.paragraph(ncr.disposition_notes)
    doc.heading("Corrective and preventive actions")
    if read["actions"]:
        doc.table(
            ["Type", "Action", "Responsible", "Due", "Status", "Verified"],
            [
                [
                    label(a["kind"]),
                    a["description"],
                    a["responsible_name"] or "-",
                    a["due_date"] or "-",
                    label(a["status"]),
                    f"{a['verified_by_name'] or ''} {(a['verified_at'] or '')[:10]}".strip() or "-",
                ]
                for a in read["actions"]
            ],
            widths=[0.11, 0.37, 0.16, 0.11, 0.11, 0.14],
        )
    else:
        doc.paragraph("None recorded.")
    doc.heading("Cost impact")
    doc.table(
        ["Rework", "Delay", "Other", "Total", "Days delay"],
        [
            [
                f"{ncr.rework_cost:.2f}",
                f"{ncr.delay_cost:.2f}",
                f"{ncr.other_cost:.2f}",
                f"{total_cost(ncr):.2f}",
                ncr.days_delay,
            ]
        ],
        numeric={0, 1, 2, 3, 4},
    )
    trail = await history(db, ncr)
    if trail:
        doc.heading("Status history")
        doc.table(
            ["When", "From", "To", "By", "Note"],
            [
                [
                    (r["changed_at"] or "")[:16].replace("T", " "),
                    label(r["from_status"]) or "-",
                    label(r["to_status"]),
                    r["changed_by_name"] or "-",
                    r["note"] or "",
                ]
                for r in trail
            ],
            widths=[0.18, 0.2, 0.2, 0.17, 0.25],
        )
    return render_pdf(doc)


EXPORT_COLUMNS = [
    ("code", "NCR"),
    ("title", "Title"),
    ("status", "Status"),
    ("severity", "Severity"),
    ("raised_on", "Raised"),
    ("raised_by_name", "Raised by"),
    ("location", "Location"),
    ("trade", "Trade"),
    ("source", "Source"),
    ("source_reference", "Source ref."),
    ("spec_reference", "Spec ref."),
    ("responsible", "Responsible"),
    ("root_cause_category", "Root cause"),
    ("disposition", "Disposition"),
    ("rework_cost", "Rework cost"),
    ("delay_cost", "Delay cost"),
    ("other_cost", "Other cost"),
    ("total_cost", "Total cost"),
    ("days_delay", "Days delay"),
    ("open_actions", "Open actions"),
]


async def export_rows(db: AsyncSession, where: list[Any]) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(Ncr).where(*where).order_by(Ncr.id))).scalars())
    read = await read_ncrs(db, rows)
    for r in read:
        r["responsible"] = r["responsible_user_name"] or r["responsible_contact_name"] or r["responsible_company_name"]
        for key in ("rework_cost", "delay_cost", "other_cost", "total_cost"):
            r[key] = float(r[key])
    return read
