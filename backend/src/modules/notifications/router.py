"""Mounted at /api/v1/notifications. Every route acts on the caller's own notifications."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy import func, select, update

from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import NotFoundException
from ..common.pagination import MAX_INTEGER_ID, ItemsPerPageDep, PageDep
from .constants import DEFAULTS, Category
from .models import Notification, NotificationPreference
from .schemas import NotificationRead, PreferenceRow, PreferencesSet, UnreadCount
from .service import unread_filter

router = APIRouter(tags=["Notifications"])

NotificationId = Annotated[int, Path(ge=1, le=MAX_INTEGER_ID)]


@router.get("/", response_model=PaginatedListResponse[NotificationRead], summary="The Caller's Notifications, Unread First")
async def list_notifications(
    db: AsyncSessionDep,
    user: CurrentUserDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 30,
    unread_only: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Any:
    filters = [Notification.user_id == user["id"]]
    if unread_only:
        filters.append(Notification.read_at.is_(None))
    if search:
        filters.append(func.lower(Notification.title).like(f"%{search.lower()}%"))
    total = await db.scalar(select(func.count()).select_from(Notification).where(*filters))
    rows = (
        await db.execute(
            select(Notification)
            .where(*filters)
            .order_by(Notification.read_at.is_not(None), Notification.created_at.desc())
            .offset(compute_offset(page, items_per_page))
            .limit(items_per_page)
        )
    ).scalars()
    data = {"data": [NotificationRead.model_validate(n).model_dump(mode="json") for n in rows], "total_count": total or 0}

    return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)


@router.get("/unread-count", response_model=UnreadCount, summary="How Many Are Unread")
async def unread_count(db: AsyncSessionDep, user: CurrentUserDep) -> UnreadCount:
    count = await db.scalar(select(func.count()).select_from(Notification).where(*unread_filter(user["id"])))
    return UnreadCount(unread=count or 0)


@router.patch("/{notification_id}/read", response_model=NotificationRead, summary="Mark Read or Unread")
async def mark_read(
    notification_id: NotificationId, db: AsyncSessionDep, user: CurrentUserDep, read: bool = True
) -> NotificationRead:
    n = await db.get(Notification, notification_id)
    if n is None or n.user_id != user["id"]:
        raise NotFoundException("No such notification")
    n.read_at = datetime.now(UTC) if read else None
    await db.commit()
    return NotificationRead.model_validate(n)


@router.post("/read-all", response_model=UnreadCount, summary="Mark Everything Read")
async def read_all(db: AsyncSessionDep, user: CurrentUserDep) -> UnreadCount:
    await db.execute(update(Notification).where(*unread_filter(user["id"])).values(read_at=datetime.now(UTC)))
    await db.commit()
    return UnreadCount(unread=0)


@router.get("/preferences", response_model=list[PreferenceRow], summary="The Caller's Notification Preferences")
async def preferences(db: AsyncSessionDep, user: CurrentUserDep) -> list[PreferenceRow]:
    rows = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user["id"]))
    stored = {p.category: p for p in rows.scalars()}
    return [
        PreferenceRow(
            category=c,
            in_app=stored[c].in_app if c in stored else DEFAULTS[c][0],
            email=stored[c].email if c in stored else DEFAULTS[c][1],
        )
        for c in Category
    ]


@router.put("/preferences", response_model=list[PreferenceRow], summary="Set Notification Preferences")
async def set_preferences(values: PreferencesSet, db: AsyncSessionDep, user: CurrentUserDep) -> list[PreferenceRow]:
    for row in values.preferences:
        pref = await db.get(NotificationPreference, (user["id"], row.category.value))
        if pref is None:
            db.add(NotificationPreference(user_id=user["id"], category=row.category.value, in_app=row.in_app, email=row.email))
        else:
            pref.in_app, pref.email = row.in_app, row.email
    await db.commit()
    return await preferences(db, user)
