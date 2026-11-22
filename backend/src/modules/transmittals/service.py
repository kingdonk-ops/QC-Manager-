from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.mail import Attachment, Mail, deliver
from ...infrastructure.pdf import Document, render_pdf
from ...infrastructure.records import next_reference, record_transition
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..contacts.models import Contact
from ..contacts.service import contact_names
from ..files.models import StoredFile
from ..projects.models import Project
from ..user.models import User
from .constants import ENTITY, PURPOSE_LABELS, Purpose, TransmittalStatus
from .models import Transmittal, TransmittalDocument, TransmittalRecipient
from .schemas import DocumentRead, RecipientRead, RevisionWarning, TransmittalRead

MAX_CHAIN = 200


class TransmittalNotFoundError(ResourceNotFoundError):
    public_detail = "Transmittal not found."


class NotDraftError(ValidationError):
    public_detail = "A transmittal can only be changed while it's a draft."


class NotSentError(ValidationError):
    public_detail = "Acknowledgements are recorded after the transmittal is sent."


class EmptyTransmittalError(ValidationError):
    public_detail = "Add at least one document and one recipient before sending."


class DocumentChoiceError(ValidationError):
    public_detail = "Choose documents from this project."


class ContactChoiceError(ValidationError):
    public_detail = "One of those contacts doesn't exist."


class RecipientNotFoundError(ResourceNotFoundError):
    public_detail = "That recipient isn't on this transmittal."


def purpose_label(purpose: str) -> str:
    return PURPOSE_LABELS.get(Purpose(purpose), purpose) if purpose in set(Purpose) else purpose


def link_of(t: Transmittal) -> str:
    return f"/transmittals?project={t.project_id}&id={t.id}"


async def get_transmittal(db: AsyncSession, transmittal_id: int) -> Transmittal:
    t = await db.get(Transmittal, transmittal_id)
    if t is None:
        raise TransmittalNotFoundError("No such transmittal")
    return t


def require_draft(t: Transmittal) -> None:
    if t.status != TransmittalStatus.DRAFT:
        raise NotDraftError(t.status)


async def latest_revisions(db: AsyncSession, file_ids: set[int]) -> dict[int, StoredFile]:
    """For each file that has been superseded, the newest revision in its chain."""
    out: dict[int, StoredFile] = {}
    if not file_ids:
        return out
    stale = list(
        (await db.execute(select(StoredFile).where(StoredFile.id.in_(file_ids), StoredFile.is_latest.is_(False)))).scalars()
    )
    for f in stale:
        current, steps = f, 0
        while steps < MAX_CHAIN:
            newer = await db.scalar(select(StoredFile).where(StoredFile.supersedes_id == current.id).order_by(StoredFile.id))
            if newer is None:
                break
            current, steps = newer, steps + 1
        out[f.id] = current
    return out


async def documents_of(db: AsyncSession, transmittal_id: int) -> list[TransmittalDocument]:
    return list(
        (
            await db.execute(
                select(TransmittalDocument)
                .where(TransmittalDocument.transmittal_id == transmittal_id)
                .order_by(TransmittalDocument.id)
            )
        ).scalars()
    )


async def recipients_of(db: AsyncSession, transmittal_ids: list[int]) -> dict[int, list[TransmittalRecipient]]:
    out: dict[int, list[TransmittalRecipient]] = defaultdict(list)
    if transmittal_ids:
        rows = (
            await db.execute(
                select(TransmittalRecipient)
                .where(TransmittalRecipient.transmittal_id.in_(transmittal_ids))
                .order_by(TransmittalRecipient.id)
            )
        ).scalars()
        for r in rows:
            out[r.transmittal_id].append(r)
    return out


def delivery_of(r: TransmittalRecipient) -> str:
    if r.acknowledged_at:
        return "acknowledged"
    if r.received_at:
        return "received"
    if r.sent_at:
        return "sent" if r.email else "no_email"
    return "pending"


async def read_documents(db: AsyncSession, docs: list[TransmittalDocument]) -> tuple[list[DocumentRead], list[RevisionWarning]]:
    latest = await latest_revisions(db, {d.file_id for d in docs if d.file_id})
    out, warnings = [], []
    for d in docs:
        newer = latest.get(d.file_id) if d.file_id else None
        read = DocumentRead.model_validate(d).model_copy(
            update={
                "is_latest": newer is None,
                "latest_file_id": newer.id if newer else d.file_id,
                "latest_revision": newer.revision if newer else d.revision,
            }
        )
        out.append(read)
        if newer is not None:
            warnings.append(
                RevisionWarning(
                    document_id=d.id,
                    file_id=d.file_id,
                    name=d.name,
                    revision=d.revision,
                    latest_file_id=newer.id,
                    latest_revision=newer.revision,
                    message=f"{d.name} rev {d.revision} has been superseded by rev {newer.revision}.",
                )
            )
    return out, warnings


async def read_transmittals(db: AsyncSession, items: list[Transmittal], *, full: bool = False) -> list[dict[str, Any]]:
    ids = [t.id for t in items]
    recipients = await recipients_of(db, ids)
    counts: dict[int, int] = {}
    if ids:
        counts = dict(
            (
                await db.execute(
                    select(TransmittalDocument.transmittal_id, func.count())
                    .where(TransmittalDocument.transmittal_id.in_(ids))
                    .group_by(TransmittalDocument.transmittal_id)
                )
            )
            .tuples()
            .all()
        )
    out = []
    for t in items:
        people = recipients[t.id]
        update: dict[str, Any] = {
            "document_count": counts.get(t.id, 0),
            "recipient_count": len(people),
            "acknowledged_count": sum(1 for r in people if r.acknowledged_at),
            "recipients": [RecipientRead.model_validate(r).model_copy(update={"delivery": delivery_of(r)}) for r in people],
        }
        if full:
            update["documents"], update["warnings"] = await read_documents(db, await documents_of(db, t.id))
        out.append(TransmittalRead.model_validate(t).model_copy(update=update).model_dump(mode="json"))
    return out


async def add_documents(db: AsyncSession, t: Transmittal, file_ids: list[int]) -> None:
    require_draft(t)
    wanted = list(dict.fromkeys(file_ids))
    files = {f.id: f for f in (await db.execute(select(StoredFile).where(StoredFile.id.in_(wanted)))).scalars()}
    if set(files) != set(wanted) or any(f.project_id != t.project_id for f in files.values()):
        raise DocumentChoiceError("bad file")
    present = {d.file_id for d in await documents_of(db, t.id)}
    for fid in wanted:
        if fid in present:
            continue
        f = files[fid]
        db.add(TransmittalDocument(transmittal_id=t.id, file_id=f.id, name=f.name, revision=f.revision, category=f.category))
    await db.flush()


async def swap_to_latest(db: AsyncSession, t: Transmittal, document: TransmittalDocument) -> None:
    require_draft(t)
    if document.file_id is None:
        return
    newer = (await latest_revisions(db, {document.file_id})).get(document.file_id)
    if newer is None:
        return
    duplicate = await db.scalar(
        select(TransmittalDocument).where(TransmittalDocument.transmittal_id == t.id, TransmittalDocument.file_id == newer.id)
    )
    if duplicate is not None:
        await db.delete(document)
    else:
        document.file_id, document.name, document.revision, document.category = (
            newer.id,
            newer.name,
            newer.revision,
            newer.category,
        )
    await db.flush()


async def add_recipients(db: AsyncSession, t: Transmittal, contact_ids: list[int]) -> None:
    require_draft(t)
    wanted = list(dict.fromkeys(contact_ids))
    contacts = {c.id: c for c in (await db.execute(select(Contact).where(Contact.id.in_(wanted)))).scalars()}
    if set(contacts) != set(wanted):
        raise ContactChoiceError("bad contact")
    names = await contact_names(db, wanted)
    present = {r.contact_id for r in (await recipients_of(db, [t.id]))[t.id]}
    for cid in wanted:
        if cid not in present:
            db.add(TransmittalRecipient(transmittal_id=t.id, contact_id=cid, name=names[cid][:300], email=contacts[cid].email))
    await db.flush()


async def create(db: AsyncSession, values: dict[str, Any], actor_id: int) -> Transmittal:
    file_ids, contact_ids = values.pop("file_ids"), values.pop("contact_ids")
    project_id = values.pop("project_id")
    t = Transmittal(
        project_id=project_id,
        code=await next_reference(db, "TR", project_id),
        subject=values.pop("subject"),
        created_by_id=actor_id,
        **{k: (v.value if hasattr(v, "value") else v) for k, v in values.items()},
    )
    db.add(t)
    await db.flush()
    await record_transition(db, ENTITY, t.id, None, TransmittalStatus.DRAFT.value, actor_id)
    if file_ids:
        await add_documents(db, t, file_ids)
    if contact_ids:
        await add_recipients(db, t, contact_ids)
    await db.commit()
    return t


async def cover_sheet(db: AsyncSession, t: Transmittal) -> bytes:
    project = await db.get(Project, t.project_id)
    assert project is not None
    docs = await documents_of(db, t.id)
    people = (await recipients_of(db, [t.id]))[t.id]
    sender_id = t.sent_by_id or t.created_by_id
    sender = await db.scalar(select(User.name).where(User.id == sender_id)) if sender_id else None
    issued = t.sent_at or datetime.now(UTC)
    doc = Document(
        title=f"Transmittal {t.code}",
        subtitle=f"{project.name} · {project.code}",
        footer=f"{project.code} · Transmittal {t.code}",
    )
    doc.fields(
        [
            ("Project", f"{project.code} {project.name}"),
            ("Transmittal", t.code),
            ("Date", issued.strftime("%d %b %Y")),
            ("Subject", t.subject),
            ("Purpose", purpose_label(t.purpose)),
            ("Response due", t.response_due.strftime("%d %b %Y") if t.response_due else "-"),
            ("From", sender or "-"),
            ("To", "\n".join(r.name for r in people) or "-"),
        ]
    )
    doc.heading("Documents")
    doc.table(
        ["No.", "Document", "Rev", "Category", "Copies"],
        [[i, d.name, d.revision, d.category.replace("_", " "), d.copies] for i, d in enumerate(docs, start=1)],
        widths=[0.07, 0.58, 0.08, 0.17, 0.1],
        numeric={0, 2, 4},
    )
    if t.notes:
        doc.heading("Notes")
        doc.paragraph(t.notes)
    doc.heading("Acknowledgement of receipt")
    doc.paragraph("Please confirm receipt of the documents listed above by signing and returning this sheet.")
    doc.table(
        ["Recipient", "Received (date)", "Signature", "Comments"],
        [[r.name, "", "", r.acknowledgement_note or ""] for r in people] or [["", "", "", ""]],
        widths=[0.3, 0.18, 0.22, 0.3],
    )
    return render_pdf(doc)


async def send(db: AsyncSession, t: Transmittal, actor: dict[str, Any], message: str | None) -> list[RevisionWarning]:
    require_draft(t)
    docs = await documents_of(db, t.id)
    people = (await recipients_of(db, [t.id]))[t.id]
    if not docs or not people:
        raise EmptyTransmittalError("empty")
    _, warnings = await read_documents(db, docs)
    now = datetime.now(UTC)
    await record_transition(db, ENTITY, t.id, t.status, TransmittalStatus.SENT.value, actor["id"])
    t.status, t.sent_at, t.sent_by_id = TransmittalStatus.SENT.value, now, actor["id"]
    for r in people:
        r.sent_at = now
    await db.flush()
    pdf = await cover_sheet(db, t)
    project = await db.get(Project, t.project_id)
    assert project is not None
    listing = "\n".join(f"  {i}. {d.name} (rev {d.revision})" for i, d in enumerate(docs, start=1))
    purpose = purpose_label(t.purpose)
    await db.commit()
    for r in people:
        if not r.email:
            continue
        text = (
            f"Dear {r.name},\n\n"
            f"Please find transmittal {t.code} for {project.name} ({project.code}): {t.subject}.\n"
            f"Purpose: {purpose}.\n\n" + (f"{message}\n\n" if message else "") + f"Documents:\n{listing}\n\n"
            "The cover sheet is attached. Please acknowledge receipt.\n\n"
            f"{actor.get('name') or ''}"
        )
        await deliver(
            Mail(
                to=[r.email],
                subject=f"Transmittal {t.code}: {t.subject}"[:200],
                text=text,
                attachments=[Attachment(f"{t.code}.pdf", pdf, "application/pdf")],
            )
        )
    return warnings


async def acknowledge(db: AsyncSession, t: Transmittal, values: dict[str, Any], actor_id: int) -> None:
    if t.status == TransmittalStatus.DRAFT:
        raise NotSentError(t.status)
    recipient = await db.get(TransmittalRecipient, values["recipient_id"])
    if recipient is None or recipient.transmittal_id != t.id:
        raise RecipientNotFoundError("no such recipient")
    now = datetime.now(UTC)
    recipient.received_at = values.get("received_at") or recipient.received_at or now
    if values.get("acknowledged", True):
        recipient.acknowledged_at = values.get("acknowledged_at") or recipient.acknowledged_at or now
    if values.get("note") is not None:
        recipient.acknowledgement_note = values["note"]
    await db.flush()
    people = (await recipients_of(db, [t.id]))[t.id]
    acknowledged = sum(1 for r in people if r.acknowledged_at)
    target = (
        TransmittalStatus.ACKNOWLEDGED
        if acknowledged == len(people)
        else TransmittalStatus.PARTIALLY_ACKNOWLEDGED
        if acknowledged
        else TransmittalStatus.SENT
    ).value
    if target != t.status:
        await record_transition(db, ENTITY, t.id, t.status, target, actor_id, f"{recipient.name} acknowledged")
        t.status = target
    await db.commit()
