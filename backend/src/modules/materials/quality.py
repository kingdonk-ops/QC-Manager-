"""Pass, fail and conditional outcomes of receipt review and PMI recording, and the automatic material reports.

Mapping: pass sets accepted, fail sets rejected, conditional sets accepted plus the conditional flag. Clients that send
only a receipt status or a PMI result keep working; the outcome is derived from it. A fail or conditional outcome
raises a material-kind report (source supplier) in the same transaction; the caller commits and then announces it."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.modules.state import is_enabled
from ..inspections import ncr_text
from ..inspections.criteria import CriterionNotFoundError, get_criterion
from ..inspections.models import AcceptanceCriterion
from ..inspections.tolerance import criterion_clause
from ..ncr.auto import raise_automatic
from ..ncr.models import Ncr
from ..ncr.service import publish_raised
from . import service
from .constants import PmiResult, ReceiptStatus
from .models import Heat, MaterialReceipt, MillCertificate, PmiTest
from .schemas import MaterialReceiptStatusIn, Outcome, PmiIn

OUTCOME_STATUS = {Outcome.PASS.value: "accepted", Outcome.FAIL.value: "rejected", Outcome.CONDITIONAL.value: "accepted"}
STATUS_OUTCOME = {ReceiptStatus.ACCEPTED.value: Outcome.PASS.value, ReceiptStatus.REJECTED.value: Outcome.FAIL.value}
RESULT_OUTCOME = {PmiResult.ACCEPTED.value: Outcome.PASS.value, PmiResult.REJECTED.value: Outcome.FAIL.value}
REPORTING = (Outcome.FAIL.value, Outcome.CONDITIONAL.value)


async def check_criterion(db: AsyncSession, project_id: int, criterion_id: int | None) -> AcceptanceCriterion | None:
    """The criterion of this project, checked only when inspections is on for it (off answers not found)."""
    if criterion_id is None:
        return None
    if not await is_enabled(db, "inspections", project_id):
        raise CriterionNotFoundError("No such criterion")
    return await get_criterion(db, criterion_id, project_id)


async def announce(report: Ncr | None) -> None:
    """Publish the raised event once the caller has committed."""
    if report is not None:
        await publish_raised(report)


# --- receipts ----------------------------------------------------------------------------------------


async def review_receipt(
    db: AsyncSession, receipt: MaterialReceipt, values: MaterialReceiptStatusIn, user_id: int
) -> Ncr | None:
    """Accept or reject a receipt, with or without an outcome. A report is raised for fail and conditional only."""
    previous = receipt.status
    if values.outcome is not None:
        if previous != ReceiptStatus.RECEIVED:
            raise service.MaterialsRuleError(f"A receipt can be reviewed only while it is received; this one is {previous}.")
        outcome: str | None = values.outcome.value
        target = OUTCOME_STATUS[values.outcome.value]
        if values.status is not None and values.status.value != target:
            raise service.MaterialsRuleError(f"The status {values.status.value} does not match the outcome {outcome}.")
    else:
        assert values.status is not None  # the body requires a status or an outcome
        target = values.status.value
        outcome = STATUS_OUTCOME.get(target) if target != previous else None
    criterion = await check_criterion(db, receipt.project_id, values.criterion_id)
    await service.change_receipt_status(db, receipt, target, values.note, user_id)
    if target == ReceiptStatus.RECEIVED:
        receipt.outcome, receipt.conditional = None, False
    elif outcome is not None:
        receipt.outcome, receipt.conditional = outcome, outcome == Outcome.CONDITIONAL.value
        receipt.criterion_id = values.criterion_id if criterion else receipt.criterion_id
        if values.measured_value is not None:
            receipt.measured_value = values.measured_value
    if outcome not in REPORTING:
        return None
    heats = list((await db.execute(select(Heat).where(Heat.receipt_id == receipt.id).order_by(Heat.id))).scalars())
    report = await _raise(
        db,
        project_id=receipt.project_id,
        kind="material_rejected" if outcome == Outcome.FAIL.value else "material_conditional",
        source_kind="material_receipt",
        record_id=receipt.id,
        number=receipt.code,
        title=receipt.supplier or receipt.delivery_note or "",
        label="material receipt",
        outcome=outcome,
        severity=values.severity,
        criterion=criterion or await _stored(db, receipt.project_id, receipt.criterion_id),
        criterion_id=receipt.criterion_id,
        measured=receipt.measured_value,
        notes=values.note or receipt.notes,
        heats=heats,
        supplier=receipt.supplier,
        user_id=user_id,
    )
    receipt.report_id = report.id if report else receipt.report_id
    return report


# --- PMI ---------------------------------------------------------------------------------------------


async def pmi_values(db: AsyncSession, heat: Heat, body: PmiIn) -> dict[str, Any]:
    """The columns of the PMI record: the stored result derived from the outcome (or the outcome from the result)."""
    outcome = body.outcome.value if body.outcome else RESULT_OUTCOME[body.result.value if body.result else ""]
    await check_criterion(db, heat.project_id, body.criterion_id)
    data = body.model_dump(exclude={"severity"})
    data.update(
        result=PmiResult.REJECTED.value if outcome == Outcome.FAIL.value else PmiResult.ACCEPTED.value,
        outcome=outcome,
        conditional=outcome == Outcome.CONDITIONAL.value,
    )
    return data


async def record_pmi_outcome(db: AsyncSession, heat: Heat, test: PmiTest, body: PmiIn, user_id: int) -> Ncr | None:
    """One report per failing or conditional test; tests of one heat are never combined into a verdict."""
    if test.outcome not in REPORTING:
        return None
    criterion = await _stored(db, heat.project_id, test.criterion_id)
    receipt = await db.get(MaterialReceipt, heat.receipt_id) if heat.receipt_id else None
    report = await _raise(
        db,
        project_id=heat.project_id,
        kind="pmi_failed" if test.outcome == Outcome.FAIL.value else "pmi_conditional",
        source_kind="pmi_test",
        record_id=test.id,
        number=heat.heat_number,
        title=f"PMI {test.tested_on.isoformat()}",
        label="PMI test",
        outcome=str(test.outcome),
        severity=body.severity,
        criterion=criterion,
        criterion_id=test.criterion_id,
        measured=test.measured_value,
        notes=test.notes,
        heats=[heat],
        supplier=receipt.supplier if receipt else None,
        user_id=user_id,
        facts={"grade_found": test.grade_found, "heat_id": heat.id, "tested_on": test.tested_on.isoformat()},
    )
    test.report_id = report.id if report else None
    return report


# --- the report --------------------------------------------------------------------------------------


async def _stored(db: AsyncSession, project_id: int, criterion_id: int | None) -> AcceptanceCriterion | None:
    if criterion_id is None or not await is_enabled(db, "inspections", project_id):
        return None
    return await db.get(AcceptanceCriterion, criterion_id)


async def _traceability(db: AsyncSession, heats: list[Heat]) -> list[str]:
    """Heat number, lot, grade, product form and manufacturer, then each heat's certificates."""
    lines: list[str] = []
    for heat in heats:
        parts = [f"heat {heat.heat_number}", f"lot {heat.lot_number}" if heat.lot_number else ""]
        parts += [f"grade {heat.material_grade}", f"product form {heat.product_form}"]
        parts += [f"manufacturer {heat.manufacturer}" if heat.manufacturer else ""]
        lines.append("Traceability: " + ", ".join(p for p in parts if p) + ".")
        certs = (await db.execute(select(MillCertificate).where(MillCertificate.heat_id == heat.id))).scalars()
        lines += [f"Certificate: type {c.certificate_type}, number {c.certificate_number}, status {c.status}." for c in certs]
    return lines


async def _raise(
    db: AsyncSession,
    *,
    project_id: int,
    kind: str,
    source_kind: str,
    record_id: int,
    number: str,
    title: str,
    label: str,
    outcome: str,
    severity: str | None,
    criterion: AcceptanceCriterion | None,
    criterion_id: int | None,
    measured: str | None,
    notes: str | None,
    heats: list[Heat],
    supplier: str | None,
    user_id: int,
    facts: dict[str, Any] | None = None,
) -> Ncr | None:
    """The material-kind report, or None when the issues module is off for the project (the outcome is still stored)."""
    if not await is_enabled(db, "ncr", project_id):
        return None
    context = [f"Supplier: {supplier}" if supplier else "", *await _traceability(db, heats)]
    return await raise_automatic(
        db,
        project_id=project_id,
        title=ncr_text.event_title(kind, number, title),
        description=ncr_text.description(
            source_label=label,
            number=number,
            result_notes=notes,
            context=context,
            clause=criterion_clause(criterion, measured) if criterion else None,
        ),
        raised_by_id=user_id,
        severity=severity or ncr_text.default_severity(outcome),
        source="supplier",
        source_reference=number,
        source_data=ncr_text.source_data(
            source_kind=source_kind,
            record_id=record_id,
            number=number,
            outcome=outcome,
            criterion_id=criterion_id,
            measured_value=measured,
            report_kind="material",
            supplier=supplier,
            heat_numbers=[h.heat_number for h in heats],
            **(facts or {}),
        ),
    )
