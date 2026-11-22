"""The MDR gate: every readiness check for a dossier, run as a dry run (the builder) or before an issue.

Checks come from three places:

* modules' ``mdr.py`` (``register_mdr_check``): inspections and NCRs ship theirs;
* guarded hooks for modules built separately (issues, ITP hold points, calibration): when the module is
  absent, switched off, or doesn't expose the function, the check reports ``not_available`` instead of failing;
* the dossier itself: a final issue needs the client's acceptance of the latest review revision.
"""

import importlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.dossier import CheckUnavailable, Finding, MdrContext, all_checks
from ...infrastructure.logging import get_logger
from ...infrastructure.modules.loader import enabled_modules
from ...infrastructure.modules.state import is_enabled
from .constants import IssuePurpose, RevisionKind, RevisionStatus
from .models import MdrRevision

logger = get_logger()
MODULES_PACKAGE = __name__.rsplit(".", 2)[0]


@dataclass(frozen=True)
class Hook:
    key: str
    title: str
    module: str
    target: str
    """``"<module>.<submodule>:<function>"`` called as ``await fn(db, project_id, node_ids)``."""
    blocking: bool = True


HOOKS: tuple[Hook, ...] = (
    Hook("issues_blocking", "No open issues that block the dossier", "ncr", "ncr.service:blocking_issues"),
    Hook(
        "itp_hold_points",
        "Every ITP hold point in scope is signed",
        "inspections",
        "inspections.eligibility:unsigned_hold_points",
    ),
    Hook(
        "equipment_calibrated",
        "Equipment used in scope was in calibration",
        "calibration",
        "calibration.service:uncalibrated_equipment",
    ),
)
"""The contract: ``async def blocking_issues(db, project_id: int, node_ids: list[int] | None) -> list[...]`` returning
``Finding``s, dicts with ``message`` (or ``title``), ``reference`` (or ``code``) and ``link``, or plain strings."""


def _finding(item: Any) -> Finding:
    if isinstance(item, Finding):
        return item
    if isinstance(item, dict):
        message = item.get("message") or item.get("title") or str(item)
        reference = item.get("reference") or item.get("code")
        if reference and reference not in message:
            message = f"{reference} {message}"
        return Finding(str(message), reference=reference, link=item.get("link"))
    return Finding(str(item))


async def _module_on(db: AsyncSession, module: str, project_id: int) -> bool:
    return module in {m.manifest.name for m in enabled_modules()} and await is_enabled(db, module, project_id)


def _row(
    key: str, title: str, module: str, blocking: bool, status: str, findings: list[Finding], detail: str | None = None
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "module": module,
        "blocking": blocking,
        "status": status,
        "findings": [{"message": f.message, "reference": f.reference, "link": f.link} for f in findings],
        "detail": detail,
    }


async def _hook(db: AsyncSession, ctx: MdrContext, hook: Hook) -> dict[str, Any]:
    if not await _module_on(db, hook.module, ctx.project_id):
        return _row(
            hook.key, hook.title, hook.module, hook.blocking, "not_available", [], f"The {hook.module} module isn't available."
        )
    path, name = hook.target.split(":")
    try:
        fn = getattr(importlib.import_module(f"{MODULES_PACKAGE}.{path}"), name)
    except (ImportError, AttributeError):
        return _row(
            hook.key, hook.title, hook.module, hook.blocking, "not_available", [], f"{hook.module} doesn't provide {name}."
        )
    findings = [_finding(i) for i in await fn(db, ctx.project_id, ctx.node_ids)]
    return _row(hook.key, hook.title, hook.module, hook.blocking, "fail" if findings else "pass", findings)


async def client_acceptance(db: AsyncSession, dossier_id: int) -> list[Finding]:
    latest = await db.scalar(
        select(MdrRevision)
        .where(
            MdrRevision.dossier_id == dossier_id,
            MdrRevision.kind == RevisionKind.REVIEW.value,
            MdrRevision.signed_at.is_not(None),
        )
        .order_by(MdrRevision.id.desc())
        .limit(1)
    )
    if latest is None:
        return [Finding("No review revision has been issued to the client yet.")]
    if latest.status != RevisionStatus.ACCEPTED.value:
        return [Finding(f"The client hasn't accepted Rev {latest.revision} (it is {latest.status.replace('_', ' ')}).")]
    return []


async def run_checks(db: AsyncSession, ctx: MdrContext, purpose: str | None) -> list[dict[str, Any]]:
    """Every check, in a stable order. ``purpose`` ``final`` adds the final-only checks; ``None`` is a draft."""
    out = []
    for check in sorted(all_checks(), key=lambda c: c.key):
        if check.final_only and purpose != IssuePurpose.FINAL:
            continue
        if not await _module_on(db, check.module, ctx.project_id):
            out.append(
                _row(
                    check.key,
                    check.title,
                    check.module,
                    check.blocking,
                    "not_available",
                    [],
                    f"The {check.module} module is switched off.",
                )
            )
            continue
        try:
            findings = await check.fn(db, ctx)
        except CheckUnavailable as exc:
            out.append(_row(check.key, check.title, check.module, check.blocking, "not_available", [], str(exc) or None))
            continue
        except Exception:
            logger.exception("MDR check failed", extra={"check": check.key})
            out.append(
                _row(check.key, check.title, check.module, check.blocking, "not_available", [], "The check failed to run.")
            )
            continue
        out.append(_row(check.key, check.title, check.module, check.blocking, "fail" if findings else "pass", findings))
    for hook in HOOKS:
        try:
            out.append(await _hook(db, ctx, hook))
        except Exception:
            logger.exception("MDR hook failed", extra={"check": hook.key})
            out.append(_row(hook.key, hook.title, hook.module, hook.blocking, "not_available", [], "The check failed to run."))
    if purpose == IssuePurpose.FINAL:
        findings = await client_acceptance(db, ctx.dossier_id)
        out.append(
            _row(
                "client_acceptance",
                "The client accepted the latest review revision",
                "mdr",
                True,
                "fail" if findings else "pass",
                findings,
            )
        )
    return out


def ready(checks: list[dict[str, Any]]) -> bool:
    return not any(c["blocking"] and c["status"] == "fail" for c in checks)
