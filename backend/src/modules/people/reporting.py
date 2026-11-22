"""The user directory as a dataset."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.reporting import Column, Dataset, register_dataset
from ..user.models import User


async def user_rows(db: AsyncSession, project_id: int | None, filters: dict[str, Any]) -> list[dict[str, Any]]:
    users = (await db.execute(select(User).order_by(User.name))).scalars()
    return [
        {
            "name": u.name,
            "email": u.email,
            "account_type": "staff" if u.entra_id or u.is_superuser else "external",
            "active": not u.is_deleted,
            "users": 1,
        }
        for u in users
    ]


register_dataset(
    Dataset(
        name="users",
        module="people",
        title="Users",
        description="Staff and external accounts.",
        project_scoped=False,
        permission="people.read",
        columns=[
            Column("name", "Name"),
            Column("email", "Email"),
            Column("account_type", "Account type"),
            Column("active", "Active", "bool"),
            Column("users", "Count", "number"),
        ],
        rows=user_rows,
    )
)
