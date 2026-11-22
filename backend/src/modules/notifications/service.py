from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import settings
from ...infrastructure.mail import Mail, deliver
from ..user.models import User
from .constants import DEFAULTS, Category
from .models import Notification, NotificationPreference


async def _preferences(db: AsyncSession, user_ids: list[int], category: str) -> dict[int, tuple[bool, bool]]:
    rows = await db.execute(
        select(NotificationPreference.user_id, NotificationPreference.in_app, NotificationPreference.email).where(
            NotificationPreference.user_id.in_(user_ids), NotificationPreference.category == category
        )
    )
    stored = {uid: (in_app, email) for uid, in_app, email in rows.all()}
    default = DEFAULTS.get(category, (True, False))

    return {uid: stored.get(uid, default) for uid in user_ids}


async def notify(
    db: AsyncSession,
    user_ids: Iterable[int],
    category: Category | str,
    title: str,
    *,
    body: str | None = None,
    link: str | None = None,
    entity: tuple[str, int] | None = None,
    actor_id: int | None = None,
) -> None:
    """Notify users, skipping the actor. Rows join the caller's transaction; email goes out now."""
    targets = sorted({uid for uid in user_ids if uid and uid != actor_id})
    if not targets:
        return
    category = str(category)
    prefs = await _preferences(db, targets, category)
    for uid in targets:
        if prefs[uid][0]:
            db.add(
                Notification(
                    user_id=uid,
                    category=category,
                    title=title[:300],
                    body=body,
                    link=link,
                    entity_type=entity[0] if entity else None,
                    entity_id=entity[1] if entity else None,
                    actor_id=actor_id,
                )
            )
    emails = [uid for uid in targets if prefs[uid][1]]
    if emails:
        addresses = (await db.execute(select(User.email).where(User.id.in_(emails), User.is_deleted.is_(False)))).scalars()
        url = f"{settings.FRONTEND_URL.rstrip('/')}{link}" if link else settings.FRONTEND_URL
        text = "\n\n".join(part for part in (title, body, f"Open: {url}") if part)
        for address in addresses:
            await deliver(Mail(to=[address], subject=title[:200], text=text))


def unread_filter(user_id: int) -> list[Any]:
    return [Notification.user_id == user_id, Notification.read_at.is_(None)]
