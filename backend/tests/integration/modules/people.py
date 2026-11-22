"""Extra accounts for multi-party tests (staff, clients, outsiders)."""

import secrets

from crudauth import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.models import User
from tests.fixtures.accounts import reset_password_budget
from tests.integration.rbac.test_user_permissions import _grant, _login

PASSWORD = "Password123!"


async def make_user(db: AsyncSession, name: str, *, staff: bool = False, email: str | None = None) -> dict:
    tag = secrets.token_hex(3)
    user = User(
        name=name,
        username=f"u{tag}",
        email=email or f"{name.lower().replace(' ', '.')}.{tag}@example.com",
        hashed_password=get_password_hash(PASSWORD),
        entra_id=f"00000000-0000-0000-0000-{secrets.token_hex(6)}" if staff else None,
    )
    db.add(user)
    await db.commit()
    await reset_password_budget(user.id)
    return {"id": user.id, "name": name, "username": user.username, "email": user.email, "password": PASSWORD}


async def grant(db: AsyncSession, user: dict, *permissions: str) -> None:
    await _grant(db, user["id"], f"r{user['id']}-{secrets.token_hex(3)}", *permissions)


async def login(client, user: dict) -> dict:
    return {"X-CSRF-Token": await _login(client, user)}
