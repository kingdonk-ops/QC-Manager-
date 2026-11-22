"""What NCRs contribute to a turnover dossier: the NCR / concession register, and the open-NCR checks."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import Finding, MdrCheck, MdrContext, MdrRecord, register_mdr_check, register_mdr_provider
from .constants import NcrStatus, Severity
from .models import Ncr
from .service import link_of

BLOCKING = (Severity.MAJOR.value, Severity.CRITICAL.value)


async def _ncrs(db: AsyncSession, ctx: MdrContext) -> list[Ncr]:
    rows = (await db.execute(select(Ncr).where(Ncr.project_id == ctx.project_id).order_by(Ncr.code))).scalars()
    return [n for n in rows if ctx.in_scope(getattr(n, "asset_node_id", None))]


async def ncr_register(db: AsyncSession, ctx: MdrContext) -> list[MdrRecord]:
    out = []
    for n in await _ncrs(db, ctx):
        notes = "; ".join(
            p
            for p in (
                n.severity,
                f"disposition {n.disposition.replace('_', ' ')}" if n.disposition else None,
                f"concession {n.concession_reference}" if n.concession_reference else None,
                f"root cause {n.root_cause_category}" if n.root_cause_category else None,
                f"closed {n.closed_at.date().isoformat()}" if n.closed_at else None,
            )
            if p
        )
        out.append(
            MdrRecord(
                reference=n.code,
                title=n.title,
                status=n.status,
                date=n.raised_on.isoformat() if n.raised_on else None,
                location=n.location,
                notes=notes,
            )
        )
    return out


async def _open(db: AsyncSession, ctx: MdrContext, blocking: bool) -> list[Finding]:
    return [
        Finding(f"{n.code} {n.title} ({n.severity}) is {n.status.replace('_', ' ')}", reference=n.code, link=link_of(n))
        for n in await _ncrs(db, ctx)
        if n.status != NcrStatus.CLOSED.value and (n.severity in BLOCKING) == blocking
    ]


async def open_major_ncrs(db: AsyncSession, ctx: MdrContext) -> list[Finding]:
    return await _open(db, ctx, True)


async def open_minor_ncrs(db: AsyncSession, ctx: MdrContext) -> list[Finding]:
    return await _open(db, ctx, False)


register_mdr_provider("ncr_register", ncr_register, module="ncr")
register_mdr_check(MdrCheck("ncr_open_major", "No open major or critical NCRs", "ncr", open_major_ncrs))
register_mdr_check(MdrCheck("ncr_open_minor", "Open minor NCRs", "ncr", open_minor_ncrs, blocking=False))
