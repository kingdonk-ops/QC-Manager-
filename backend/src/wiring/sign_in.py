"""What runs on every OAuth sign-in, after the profile refresh.

Imports and literals only. Each hook is called as ``hook(user, info, db)`` and commits its own writes.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from crudauth.oauth import OAuthUserInfo
from sqlalchemy.ext.asyncio import AsyncSession

from ..modules.team.entra_sync import sync_access_from_sign_in

OAuthLoginHook = Callable[[dict[str, Any], OAuthUserInfo, AsyncSession], Awaitable[None]]

OAUTH_LOGIN_HOOKS: tuple[OAuthLoginHook, ...] = (sync_access_from_sign_in,)
