"""The dossier issue override: a manager lets a dossier issue past outstanding quality holds and open blocking issues
with a mandatory reason. No FastAPI imports.

One unit of work: the documentation report is raised first (not committed), the override record stores the blocker
snapshot, the covered pending gates are annotated (never closed), one audit entry is written, and everything commits
together; the report event is published only after the commit. Any failure rolls the whole action back.

The inspections and issues modules are reached through guarded lazy lookups, never imported here, and a covered check
that cannot run refuses the override (fail closed). The caller loads the dossier under a row lock, so two overrides on
one dossier run one after the other."""

import importlib
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.audit_ledger import record_audit
from ...infrastructure.http_exceptions import ConflictException
from ...infrastructure.logging import get_logger
from . import override_rules as rules
from . import service
from .constants import CAN_ISSUE, ENTITY
from .gate import _module_on
from .models import MdrDossier, MdrOverride
from .service import MdrRuleError

logger = get_logger()
MODULES_PACKAGE = __name__.rsplit(".", 2)[0]
REPORT_SOURCE = "other"
REPORT_CATEGORY = "documentation"
"""The issues module's documentation category; its default template raises a non-blocking report."""
REPORT_MDR_EFFECT = "register_only"
REPORT_COMPLETION_EFFECT = "none"
"""Set explicitly as well, so the report never blocks any dossier or work completion even if a project edits the
template: it stays open and visible in the register, and is worked and closed like any other report."""


def _lookup(target: str) -> Any:
    """``"<module>.<submodule>:<name>"`` imported on demand; a missing module or name is not available."""
    path, name = target.split(":")
    try:
        return getattr(importlib.import_module(f"{MODULES_PACKAGE}.{path}"), name)
    except (ImportError, AttributeError):
        return None


async def history(db: AsyncSession, dossier: MdrDossier) -> list[MdrOverride]:
    rows = await db.execute(select(MdrOverride).where(MdrOverride.dossier_id == dossier.id).order_by(MdrOverride.id.desc()))
    return list(rows.scalars())


async def _raise_report(
    db: AsyncSession,
    dossier: MdrDossier,
    *,
    reference: str,
    purpose: str,
    reason: str,
    severity: str,
    blockers: list[dict[str, Any]],
    user_id: int,
) -> Any:
    """The documentation non-conformance report, created without committing. Failing to create it fails the action."""
    raise_automatic = _lookup("ncr.auto:raise_automatic")
    if raise_automatic is None:
        raise MdrRuleError("The issues module can't raise the documentation report, so the dossier is not overridden.")
    return await raise_automatic(
        db,
        project_id=dossier.project_id,
        title=rules.report_title(dossier.code, reference),
        description=rules.report_description(dossier.code, reference, purpose, reason, blockers),
        raised_by_id=user_id,
        severity=severity,
        source=REPORT_SOURCE,
        category=REPORT_CATEGORY,
        mdr_effect=REPORT_MDR_EFFECT,
        completion_effect=REPORT_COMPLETION_EFFECT,
        source_reference=reference,
        source_data=rules.report_source_data(dossier.id, reference, severity, blockers),
    )


async def _annotate(db: AsyncSession, dossier: MdrDossier, numbers: list[str], override: MdrOverride) -> list[str]:
    """Stamp the covered pending gates through the inspections module; returns the numbers actually annotated."""
    if not numbers:
        return []
    annotate = _lookup("inspections.gates:annotate_pending")
    if annotate is None:
        raise MdrRuleError("The quality gates can't be annotated, so the dossier is not overridden.")
    annotated = await annotate(db, dossier.project_id, numbers, override.id, override.reference)
    return [g.number for g in annotated]


async def record_override(
    db: AsyncSession, dossier: MdrDossier, *, purpose: str, reason: str, severity: str | None, user_id: int
) -> MdrOverride:
    """Record one override for ``purpose``. Refusals (all before anything is written): an empty reason, a dossier that
    cannot be issued for the purpose, a covered check that is not available, a failing blocking check that may never
    be overridden, a finding with no reference (all validation failures) and nothing that blocks (a conflict).
    Rolls back before raising."""
    try:
        reason = rules.clean_reason(reason)
        if not reason:
            raise MdrRuleError("Give the reason for the override.")
        try:
            chosen = rules.normalise_severity(severity)
        except ValueError as exc:
            raise MdrRuleError(str(exc)) from exc
        if dossier.status not in CAN_ISSUE[purpose]:
            raise MdrRuleError(
                f"A {purpose} revision can't be issued while the dossier is {dossier.status.replace('_', ' ')}, "
                "so there is nothing to override."
            )
        assessment = rules.assess(await service.gate(db, dossier, purpose))
        if assessment.refusal:
            raise MdrRuleError(assessment.refusal)
        if not assessment.blockers:
            raise ConflictException("Nothing blocks the issue of this dossier, so there is nothing to override.")

        count = await db.scalar(select(func.count()).select_from(MdrOverride).where(MdrOverride.dossier_id == dossier.id))
        reference = rules.override_reference(dossier.code, (count or 0) + 1)
        report = await _raise_report(
            db,
            dossier,
            reference=reference,
            purpose=purpose,
            reason=reason,
            severity=chosen,
            blockers=assessment.blockers,
            user_id=user_id,
        )
        override = MdrOverride(
            dossier_id=dossier.id,
            project_id=dossier.project_id,
            reference=reference,
            purpose=purpose,
            reason=reason,
            severity=chosen,
            blockers=[dict(b) for b in assessment.blockers],
            report_id=report.id,
            report_code=report.code,
            created_by_id=user_id,
        )
        db.add(override)
        await db.flush()
        override.gate_numbers = await _annotate(db, dossier, rules.gate_numbers(assessment.blockers), override)
        await record_audit(
            db,
            "mdr.dossier.overridden",
            ENTITY,
            dossier.id,
            actor_id=user_id,
            project_id=dossier.project_id,
            summary=f"{dossier.code} issue override {reference}; report {report.code}",
            after={
                "override_id": override.id,
                "reference": reference,
                "purpose": purpose,
                "severity": chosen,
                "reason": reason,
                "report_id": report.id,
                "report_code": report.code,
                "gate_numbers": override.gate_numbers,
                "blockers": [b["reference"] for b in assessment.blockers],
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    publish_raised = _lookup("ncr.service:publish_raised")
    if publish_raised is not None:
        try:
            await publish_raised(report)
        except Exception:
            logger.exception("The override's report event failed to publish", extra={"dossier_id": dossier.id})
    return override


async def open_report_count(db: AsyncSession, dossier: MdrDossier) -> int | None:
    """Documentation reports raised by this dossier's overrides that are not closed; ``None`` without the issues module."""
    if not await _module_on(db, "ncr", dossier.project_id):
        return None
    model, terminal = _lookup("ncr.models:Ncr"), _lookup("ncr.constants:TERMINAL")
    if model is None or terminal is None:
        return None
    stored = await db.execute(select(MdrOverride.report_id).where(MdrOverride.dossier_id == dossier.id))
    ids = [i for i in stored.scalars() if i]
    if not ids:
        return 0
    open_ = select(func.count()).select_from(model).where(model.id.in_(ids), model.status.not_in(terminal))
    return int(await db.scalar(open_) or 0)


async def gate_counts(db: AsyncSession, dossier: MdrDossier) -> dict[str, int | None]:
    """Plain pending holds, overridden-pending holds and open reports for the dossier gate response."""
    plain: int | None = None
    overridden: int | None = None
    counts = _lookup("inspections.gates:pending_hold_counts")
    if counts is not None and await _module_on(db, "inspections", dossier.project_id):
        try:
            held = await counts(db, dossier.project_id, await service.scope_nodes(db, dossier), dossier.id)
            plain, overridden = held["plain"], held["overridden"]
        except Exception:
            logger.exception("The hold counts failed to load", extra={"dossier_id": dossier.id})
    reports: int | None = None
    try:
        reports = await open_report_count(db, dossier)
    except Exception:
        logger.exception("The open report count failed to load", extra={"dossier_id": dossier.id})
    return rules.counts_payload(plain, overridden, reports)
