"""A small Microsoft Graph client, app-only (client credentials), for reading group members.

Needs the application permission ``GroupMember.Read.All`` on the app registration, with admin
consent. Nothing here writes to Entra.
"""

from typing import Any

import httpx

from ...infrastructure.auth.entra import AUTHORITY
from ...infrastructure.config.settings import settings

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
HTTP_TIMEOUT_SECONDS = 20.0


def graph_configured() -> bool:
    return bool(settings.OAUTH_ENTRA_TENANT_ID and settings.OAUTH_ENTRA_CLIENT_ID and settings.OAUTH_ENTRA_CLIENT_SECRET)


class GraphClient:
    """One app-only token, reused for every call made through this client."""

    def __init__(self, transport: Any | None = None) -> None:
        self._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, transport=transport)
        self._token: str | None = None

    async def __aenter__(self) -> "GraphClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._http.aclose()

    async def _bearer(self) -> str:
        if self._token is None:
            response = await self._http.post(
                f"{AUTHORITY}/{settings.OAUTH_ENTRA_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.OAUTH_ENTRA_CLIENT_ID,
                    "client_secret": settings.OAUTH_ENTRA_CLIENT_SECRET,
                    "scope": GRAPH_SCOPE,
                },
            )
            response.raise_for_status()
            self._token = response.json()["access_token"]

        return self._token

    async def group_member_ids(self, group_id: str) -> set[str]:
        """Object ids of every user in the group, nested groups included."""
        url: str | None = f"{GRAPH}/groups/{group_id}/transitiveMembers/microsoft.graph.user?$select=id&$top=999"
        members: set[str] = set()
        headers = {"Authorization": f"Bearer {await self._bearer()}", "ConsistencyLevel": "eventual"}
        while url:
            response = await self._http.get(url, headers=headers)
            response.raise_for_status()
            page = response.json()
            members.update(str(item["id"]).lower() for item in page.get("value", []) if item.get("id"))
            url = page.get("@odata.nextLink")

        return members
