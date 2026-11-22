"""The Graph sync of every Entra-linked team, shared by the scheduled task and ``POST /entra/sync``."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.logging import get_logger
from .entra_sync import set_team_members_from_group
from .exceptions import GraphNotConfiguredError
from .graph import GraphClient, graph_configured
from .models import Team
from .schemas import SyncReport

logger = get_logger()


async def sync_all_linked_teams(db: AsyncSession, transport: Any | None = None) -> SyncReport:
    """Refresh each linked team from its group. A group that fails is reported and the rest carry on."""
    if not graph_configured():
        raise GraphNotConfiguredError("Entra credentials are not configured")

    report = SyncReport()
    teams = (await db.execute(select(Team.id, Team.name, Team.entra_group_id).where(Team.entra_group_id.is_not(None)))).all()
    async with GraphClient(transport=transport) as graph:
        for team_id, name, group_id in teams:
            try:
                members = await graph.group_member_ids(group_id)
                outcome = await set_team_members_from_group(db, team_id, members)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Graph sync failed for a team", extra={"team_id": team_id})
                report.teams_failed.append(name)
                continue

            report.teams_synced += 1
            report.memberships_added += outcome["added"]
            report.memberships_removed += outcome["removed"]
            report.unknown_users_skipped += outcome["unknown"]

    logger.info("Entra group sync finished", extra=report.model_dump())

    return report
