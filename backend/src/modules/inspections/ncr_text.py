"""Pure wording for automatically raised non-conformance reports: the title, the description and the structured
source data. Imports neither the web framework nor the database layer, so materials and as-built records reuse the
same builders (and the criterion clause from ``tolerance``)."""

from typing import Any

TITLE_MAX = 300
DESCRIPTION_MAX = 4000
EVENT_LABELS = {
    "inspection_failed": "Failed inspection",
    "inspection_conditional": "Conditionally accepted inspection",
    "item_failed": "Failed inspection item",
    "material_rejected": "Rejected material",
    "material_conditional": "Conditionally accepted material",
    "pmi_failed": "Failed PMI test",
    "pmi_conditional": "Conditionally accepted PMI test",
    "as_built_out_of_tolerance": "Out-of-tolerance as-built",
}
DEFAULT_SEVERITY = {"fail": "major", "conditional": "minor"}


def default_severity(outcome: str) -> str:
    """Fail defaults to major and conditional acceptance to minor; a caller-supplied severity overrides it."""
    return DEFAULT_SEVERITY.get(outcome, "minor")


def event_title(kind: str, number: str, title: str) -> str:
    """The kind of event, then the record number and title, bounded."""
    return f"{EVENT_LABELS.get(kind, kind)} {number} {title}".strip()[:TITLE_MAX]


def description(
    *,
    source_label: str,
    number: str,
    record_description: str | None = None,
    result_notes: str | None = None,
    context: list[str] | None = None,
    clause: str | None = None,
) -> str:
    """Raised automatically from the named record, then its own text and result notes, kind-specific context
    lines, and the criterion clause when there is one (the measured value appears only inside the clause)."""
    lines = [f"Raised automatically from {source_label} {number}."]
    if record_description:
        lines.append(record_description.strip())
    if result_notes:
        lines.append(f"Result notes: {result_notes.strip()}")
    lines += [c for c in (context or []) if c]
    if clause:
        lines.append(clause)
    return "\n".join(lines)[:DESCRIPTION_MAX]


def source_data(
    *,
    source_kind: str,
    record_id: int,
    number: str,
    outcome: str,
    criterion_id: int | None,
    measured_value: Any,
    report_kind: str = "workmanship",
    **facts: Any,
) -> dict[str, Any]:
    """The structured facts stored on the report, whether or not a criterion is linked."""
    return {
        "automatic": True,
        "source_kind": source_kind,
        "record_id": record_id,
        "record_number": number,
        "outcome": outcome,
        "criterion_id": criterion_id,
        "measured_value": None if measured_value is None else str(measured_value),
        "report_kind": report_kind,
        **facts,
    }
