from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.http_exceptions import UnprocessableEntityException
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError
from ..files.models import StoredFile
from ..files.service import readable_file
from ..notifications.constants import Category
from ..notifications.service import notify
from ..user.models import User
from . import geometry
from .models import Markup, MarkupCalibration, MarkupSet, StampTemplate
from .permissions import MarkupPermissionName as P
from .schemas import MarkupRead, MarkupSetRead

DEFAULT_STAMPS = [
    ("Approved", "#16a34a"),
    ("Approved as noted", "#65a30d"),
    ("Rejected", "#dc2626"),
    ("Reviewed", "#2563eb"),
    ("For Construction", "#7c3aed"),
]


class MarkupNotFoundError(ResourceNotFoundError):
    public_detail = "Markup not found."


class NotYoursError(PermissionDeniedError):
    public_detail = "Only its author, or someone allowed to change anyone's markups, can do that."


async def drawing(db: AsyncSession, file_id: int, user: dict[str, Any], held: frozenset[str]) -> StoredFile:
    """A PDF the user may read, in a project."""
    f = await readable_file(db, file_id, user, held)
    if f.project_id is None:
        raise UnprocessableEntityException("Only a project's documents can be marked up.")
    if f.content_type != "application/pdf" and not f.name.lower().endswith(".pdf"):
        raise UnprocessableEntityException("Only PDF files can be marked up.")
    return f


def may_change(row_author: int | None, user: dict[str, Any], held: frozenset[str], other: P) -> None:
    if row_author == user["id"] or other.value in held or user.get("is_superuser"):
        return
    raise NotYoursError("Not the author")


async def _names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).tuples().all())


async def read_markups(db: AsyncSession, rows: list[Markup]) -> list[dict[str, Any]]:
    names = await _names(db, {r.author_id for r in rows if r.author_id})
    return [
        MarkupRead.model_validate(r)
        .model_copy(update={"author_name": names.get(r.author_id) if r.author_id else None})
        .model_dump(mode="json")
        for r in rows
    ]


async def read_sets(db: AsyncSession, rows: list[MarkupSet]) -> list[dict[str, Any]]:
    names = await _names(db, {r.author_id for r in rows if r.author_id})
    ids = [r.id for r in rows]
    counts: dict[int, int] = {}
    if ids:
        result = await db.execute(select(Markup.set_id, func.count()).where(Markup.set_id.in_(ids)).group_by(Markup.set_id))
        counts = dict(result.tuples().all())
    return [
        MarkupSetRead.model_validate(r)
        .model_copy(
            update={"author_name": names.get(r.author_id) if r.author_id else None, "markup_count": counts.get(r.id, 0)}
        )
        .model_dump(mode="json")
        for r in rows
    ]


async def new_set(db: AsyncSession, f: StoredFile, name: str, user: dict[str, Any]) -> MarkupSet:
    assert f.project_id is not None
    row = MarkupSet(file_id=f.id, project_id=f.project_id, name=name, revision=f.revision, author_id=user["id"])
    db.add(row)
    await db.flush()
    if f.uploaded_by_id and f.uploaded_by_id != user["id"]:
        await notify(
            db,
            [f.uploaded_by_id],
            Category.MENTION,
            f"{user.get('name') or 'Someone'} is marking up {f.name}",
            body=f"Markup set: {name}",
            link=f"/markups/{f.id}?set={row.id}",
            entity=("markup_set", row.id),
            actor_id=user["id"],
        )
    return row


async def own_set(db: AsyncSession, f: StoredFile, user: dict[str, Any]) -> MarkupSet:
    existing = await db.scalar(
        select(MarkupSet).where(MarkupSet.file_id == f.id, MarkupSet.author_id == user["id"]).order_by(MarkupSet.id).limit(1)
    )
    return existing or await new_set(db, f, f"Markups by {user.get('name') or user.get('username') or 'me'}", user)


async def get_set(db: AsyncSession, set_id: int) -> MarkupSet:
    row = await db.get(MarkupSet, set_id)
    if row is None:
        raise MarkupNotFoundError("No such set")
    return row


async def get_markup(db: AsyncSession, markup_id: int) -> Markup:
    row = await db.get(Markup, markup_id)
    if row is None:
        raise MarkupNotFoundError("No such markup")
    return row


def checked_geometry(kind: str, value: dict[str, Any]) -> dict[str, Any]:
    try:
        return geometry.normalise(kind, value)
    except geometry.GeometryError as exc:
        raise UnprocessableEntityException(str(exc)) from exc


async def calibration(db: AsyncSession, file_id: int, page: int) -> MarkupCalibration | None:
    return await db.get(MarkupCalibration, (file_id, page))


async def measure(db: AsyncSession, m: Markup) -> None:
    """Fill in the measurement of a measure markup from its page's calibration (or clear it)."""
    if m.type not in geometry.MEASURE_TYPES:
        m.measurement = None
        return
    cal = await calibration(db, m.file_id, m.page)
    m.measurement = geometry.measure(m.type, m.geometry["points"], cal.meters_per_unit) if cal else None


async def remeasure_page(db: AsyncSession, file_id: int, page: int) -> None:
    rows = (
        await db.scalars(
            select(Markup).where(Markup.file_id == file_id, Markup.page == page, Markup.type.in_(geometry.MEASURE_TYPES))
        )
    ).all()
    for m in rows:
        await measure(db, m)


async def stamps(db: AsyncSession, project_id: int) -> None:
    """Give a project the standard stamps the first time anyone looks."""
    if await db.scalar(select(func.count()).select_from(StampTemplate).where(StampTemplate.project_id == project_id)):
        return
    for i, (label, color) in enumerate(DEFAULT_STAMPS):
        db.add(StampTemplate(project_id=project_id, label=label, color=color, position=i))
    await db.commit()
