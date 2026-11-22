"""Microsoft Entra ID sign-in, as a crudauth OAuth provider named ``entra``.

crudauth's generic OIDC provider reads the profile from ``/userinfo``. Entra's userinfo endpoint
answers neither ``email_verified`` nor the ``roles`` and ``groups`` claims this app maps onto roles
and teams, so this provider reads the ID token the token endpoint returned instead, after verifying
it against the tenant's published signing keys:

* the signature (RS256, a key from the tenant's JWKS),
* ``iss`` is this tenant's v2.0 issuer and ``tid`` is this tenant, so a token minted for another
  tenant (a guest's home tenant, or any multi-tenant app) is refused,
* ``aud`` is this app's client id, and ``exp`` / ``nbf`` / ``iat`` hold.

crudauth's callback calls ``exchange_code`` and then ``get_user_info(access_token)`` on one shared
provider instance. The verified claims are handed from the first to the second through a
``ContextVar``, which is local to the request's task, so two concurrent sign-ins can never read
each other's claims.

The account is linked on ``oid``: the user's object id, stable for the life of the account and the
same id Microsoft Graph returns, which is what the scheduled group sync matches users on.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

import httpx
import jwt
from crudauth.oauth import OAuthUserInfo
from crudauth.oauth.provider import AbstractOAuthProvider

from ..logging import get_logger

logger = get_logger()

PROVIDER_NAME = "entra"
AUTHORITY = "https://login.microsoftonline.com"
DEFAULT_SCOPES = ["openid", "profile", "email"]
HTTP_TIMEOUT_SECONDS = 10.0
CLOCK_SKEW_SECONDS = 120
JWKS_MIN_REFRESH_SECONDS = 300
"""An unknown ``kid`` refetches the key set, but no more often than this."""

_verified_claims: ContextVar[tuple[str, dict[str, Any]] | None] = ContextVar("entra_verified_claims", default=None)


class EntraTokenError(ValueError):
    """The ID token was missing or failed verification. crudauth's callback answers ``oauth_failed``."""


class EntraIDProvider(AbstractOAuthProvider):
    """Single-tenant Entra ID over the v2.0 endpoints. Bind the tenant with ``for_tenant``."""

    requires_client_secret = True
    tenant_id: str = ""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        *,
        transport: Any | None = None,
    ):
        if not self.tenant_id:
            raise ValueError("EntraIDProvider needs a tenant: register EntraIDProvider.for_tenant(tenant_id).")

        base = f"{AUTHORITY}/{self.tenant_id}"
        super().__init__(
            client_id,
            client_secret,
            redirect_uri,
            scopes=scopes or list(DEFAULT_SCOPES),
            authorize_endpoint=f"{base}/oauth2/v2.0/authorize",
            token_endpoint=f"{base}/oauth2/v2.0/token",
            userinfo_endpoint="",
            provider_name=PROVIDER_NAME,
            transport=transport,
        )
        self.issuer = f"{base}/v2.0"
        self.jwks_uri = f"{base}/discovery/v2.0/keys"
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_fetched_at = 0.0

    @classmethod
    def for_tenant(cls, tenant_id: str) -> type[EntraIDProvider]:
        """A subclass bound to ``tenant_id``, for crudauth's factory, which constructs providers itself."""
        if not tenant_id:
            raise ValueError("An Entra tenant id is required.")

        return type("BoundEntraIDProvider", (cls,), {"tenant_id": tenant_id})

    # --- signing keys ----------------------------------------------------------------------
    async def initialize(self) -> None:
        """Fetch the tenant's signing keys at startup, so a misconfigured tenant fails fast."""
        await self._refresh_keys()

    async def _refresh_keys(self) -> None:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, transport=self.transport) as client:
            response = await client.get(self.jwks_uri, headers={"Accept": "application/json"})
            response.raise_for_status()
            document = response.json()

        keys: dict[str, jwt.PyJWK] = {}
        for entry in document.get("keys", []):
            kid = entry.get("kid")
            if not kid or entry.get("kty") != "RSA":
                continue
            try:
                keys[kid] = jwt.PyJWK(entry, algorithm="RS256")
            except jwt.PyJWTError:
                logger.warning("Skipping an Entra signing key that could not be loaded", extra={"kid": kid})

        if not keys:
            raise EntraTokenError(f"No usable signing keys at {self.jwks_uri}.")

        self._keys = keys
        self._keys_fetched_at = time.monotonic()

    async def _key_for(self, kid: str) -> jwt.PyJWK:
        if kid not in self._keys and time.monotonic() - self._keys_fetched_at > JWKS_MIN_REFRESH_SECONDS:
            await self._refresh_keys()
        key = self._keys.get(kid)
        if key is None:
            raise EntraTokenError("The ID token is signed with a key this tenant does not publish.")

        return key

    async def verify_id_token(self, id_token: str) -> dict[str, Any]:
        """The ID token's claims, once its signature, issuer, tenant, audience and lifetime hold.

        Raises:
            EntraTokenError: Any of them doesn't.
        """
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise EntraTokenError("The ID token is malformed.") from exc

        if header.get("alg") != "RS256" or not header.get("kid"):
            raise EntraTokenError("The ID token is not RS256-signed with a key id.")

        key = await self._key_for(header["kid"])
        try:
            claims = jwt.decode(
                id_token,
                key=key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "oid", "tid"]},
            )
        except jwt.PyJWTError as exc:
            raise EntraTokenError(f"The ID token failed verification: {exc}") from exc

        if claims.get("tid") != self.tenant_id:
            raise EntraTokenError("The ID token was issued for another tenant.")

        return claims

    # --- the callback's three steps ----------------------------------------------------------
    async def exchange_code(
        self,
        code: str,
        code_verifier: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Redeem the code, then verify the ID token that came with it."""
        _verified_claims.set(None)
        token = await super().exchange_code(code, code_verifier=code_verifier, headers=headers)
        id_token = token.get("id_token") if isinstance(token, dict) else None
        access_token = token.get("access_token") if isinstance(token, dict) else None
        if not id_token or not access_token:
            raise EntraTokenError("The token endpoint returned no ID token; is the 'openid' scope requested?")

        claims = await self.verify_id_token(id_token)
        _verified_claims.set((access_token, claims))

        return token

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """The claims ``exchange_code`` verified for this same access token, in this same request."""
        held = _verified_claims.get()
        _verified_claims.set(None)
        if held is None or held[0] != access_token:
            raise EntraTokenError("No verified ID token for this sign-in.")

        return held[1]

    async def process_user_info(self, user_info: dict[str, Any]) -> OAuthUserInfo:
        """Map the verified claims onto crudauth's profile.

        The address is the ``email`` optional claim where the app registration emits it, and the
        sign-in name (UPN) otherwise. Both are set by the tenant's administrators, and the token
        is pinned to this one tenant, so the address is treated as verified. That is what lets the
        first Entra sign-in link onto an existing local account with the same address.
        """
        email = user_info.get("email") or user_info.get("preferred_username")
        if email and "@" not in email:
            email = None

        return OAuthUserInfo(
            provider=PROVIDER_NAME,
            provider_user_id=str(user_info["oid"]),
            email=email.lower() if email else None,
            email_verified=bool(email),
            name=user_info.get("name"),
            given_name=user_info.get("given_name"),
            family_name=user_info.get("family_name"),
            username=(user_info.get("preferred_username") or "").split("@", 1)[0] or None,
            picture=None,
            raw_data=user_info,
        )


def app_roles_of(info: OAuthUserInfo) -> list[str] | None:
    """The app-role values in the sign-in's token, or ``None`` for a non-Entra sign-in."""
    if info.provider != PROVIDER_NAME:
        return None
    roles = info.raw_data.get("roles") or []

    return [str(role) for role in roles if isinstance(role, str)]


def groups_of(info: OAuthUserInfo) -> list[str] | None:
    """The group object ids in the sign-in's token.

    ``None`` for a non-Entra sign-in, and also when Entra left the groups out because the user is
    in too many of them (the "groups overage" claim). The scheduled Graph sync fills those in, so a
    sign-in must not read an absent list as "in no groups".
    """
    if info.provider != PROVIDER_NAME:
        return None
    claim_names = info.raw_data.get("_claim_names") or {}
    if isinstance(claim_names, dict) and "groups" in claim_names:
        return None
    groups = info.raw_data.get("groups") or []

    return [str(group).lower() for group in groups if isinstance(group, str)]
