"""The starting library: categories and issue templates (punch and NCR per discipline, plus internal-audit
findings), seeded once as library rows (``project_id`` NULL) the first time the issues engine is used."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import DOCUMENTATION_CATEGORY, DOCUMENTATION_FLAGS, DOCUMENTATION_TEMPLATE_KEY, RevisionStatus
from .models import IssueCategory, IssueDefaultTemplate, IssueTemplate, IssueTemplateRevision

F = dict[str, Any]

CATEGORIES: list[tuple[str, str, bool]] = [
    ("general", "General", False),
    ("insulation", "Insulation", False),
    ("cladding", "Cladding", False),
    ("coatings", "Coatings", False),
    ("painting", "Painting", False),
    ("blasting", "Blasting", False),
    ("refractory", "Refractory", False),
    ("scaffolding", "Scaffolding", False),
    ("welding", "Welding", False),
    ("piping", "Piping", False),
    ("mechanical", "Mechanical", False),
    ("electrical", "Electrical", False),
    ("civil", "Civil", False),
    ("health_safety", "Health and safety", True),
    ("audit", "Audit", True),
    ("vehicle", "Vehicle", True),
    ("equipment", "Equipment", True),
    ("pre_start", "Pre-start", True),
    (DOCUMENTATION_CATEGORY, "Documentation", True),
]


def field(key: str, label: str, type: str = "text", step: str = "raise", required: bool = False, **extra: Any) -> F:
    return {"key": key, "label": label, "type": type, "step": step, "required": required, **extra}


def photos(step: str = "raise", label: str = "Photos") -> F:
    return field("photos" if step == "raise" else f"{step}_photos", label, "photo", step)


PUNCH_COMMON = [
    photos(),
    field("rectification", "What was done", "textarea", "rectify", True),
    photos("rectify", "Photos after rectification"),
    field("verification_notes", "Verification notes", "textarea", "verify"),
]

NCR_COMMON = [
    field("requirement", "Requirement not met (spec / drawing clause)", "text", "raise", True),
    photos(),
    field("containment_action", "Containment: what was quarantined, tagged or stopped", "textarea", "containment", True),
    field("use_5_whys", "Use 5-whys", "checkbox", "root_cause"),
    *[field(f"why_{n}", f"Why {n}?", "text", "root_cause") for n in range(1, 6)],
    field("effectiveness_evidence", "Evidence the actions were effective", "textarea", "effectiveness", True),
]

DISCIPLINES: dict[str, dict[str, list[F]]] = {
    "general": {"punch": [], "ncr": []},
    "insulation": {
        "punch": [
            field("defect", "Defect", "select", options=["Gaps / joints open", "Damaged", "Wet", "Missing", "Thickness"]),
            field("system_temp", "Service", "select", options=["Hot", "Cold", "Personnel protection", "Acoustic"]),
        ],
        "ncr": [
            field("material", "Insulation material"),
            field("thickness_mm", "Measured thickness", "number", unit="mm", min=0),
        ],
    },
    "cladding": {
        "punch": [
            field(
                "defect", "Defect", "select", options=["Laps facing weather", "Dent", "Missing screws", "Sealant", "Banding"]
            ),
        ],
        "ncr": [field("cladding_material", "Cladding material", "select", options=["Aluminium", "Stainless", "Galvanised"])],
    },
    "coatings": {
        "punch": [
            field("defect", "Defect", "select", options=["Holiday", "Runs / sags", "Damage", "Low DFT", "Contamination"]),
        ],
        "ncr": [
            field("coating_system", "Coating system", required=True),
            field("dft_measured_um", "Measured DFT", "number", unit="µm", min=0),
            field("dft_specified_um", "Specified DFT", "number", unit="µm", min=0),
        ],
    },
    "refractory": {
        "punch": [field("defect", "Defect", "select", options=["Cracking", "Spalling", "Anchor exposed", "Thickness"])],
        "ncr": [
            field("refractory_product", "Product / batch"),
            field("cure_dryout", "Cure / dry-out record reference"),
        ],
    },
    "scaffolding": {
        "punch": [
            field("scaffold_tag", "Scaffold tag", required=True),
            field("defect", "Defect", "select", options=["Missing toe board", "Handrail", "Ties", "Base plates", "Tag"]),
        ],
        "ncr": [field("scaffold_tag", "Scaffold tag", required=True)],
    },
    "welding": {
        "punch": [field("weld_id", "Weld ID"), field("defect", "Defect", "select", options=["Undercut", "Spatter", "Profile"])],
        "ncr": [
            field("weld_id", "Weld ID", required=True),
            field("wps", "WPS"),
            field("ndt_report", "NDT report"),
            field("defect", "Defect", "select", options=["Porosity", "Lack of fusion", "Crack", "Undercut", "Slag"]),
        ],
    },
    "health_safety": {
        "punch": [
            field("hazard", "Hazard", "select", options=["Housekeeping", "Access", "Working at height", "Energy", "PPE"]),
            field("immediate_action", "Immediate action taken", "textarea"),
        ],
        "ncr": [field("hazard", "Hazard", required=True), field("people_at_risk", "People at risk", "number", min=0)],
    },
}

DEFAULT_FLAGS: dict[str, F] = {
    # system-default punch templates use Cat A and block the MDR until closed
    "punch": {
        "default_origin": "qa",
        "default_visibility": "internal",
        "default_mdr_effect": "blocks",
        "completion_effect": "blocks",
        "default_punch_category": "B",
    },
    "ncr": {
        "default_origin": "qa",
        "default_visibility": "internal",
        "default_mdr_effect": "blocks",
        "completion_effect": "blocks",
        "default_severity": "minor",
    },
}

AUDIT_FLAGS: F = {
    "default_origin": "internal_audit",
    "default_visibility": "internal",
    "default_mdr_effect": "excluded",
    "completion_effect": "none",
}


def library() -> list[F]:
    """Every starting template: key, name, type, category, fields and flags."""
    out: list[F] = []
    for category, by_type in DISCIPLINES.items():
        label = dict((k, lbl) for k, lbl, _ in CATEGORIES)[category]
        for issue_type, extra in by_type.items():
            common = PUNCH_COMMON if issue_type == "punch" else NCR_COMMON
            out.append(
                {
                    "key": f"{category}-{issue_type}",
                    "name": f"{label} {'punch' if issue_type == 'punch' else 'NCR'}",
                    "issue_type": issue_type,
                    "category": category,
                    "fields": [*extra, *common],
                    **DEFAULT_FLAGS[issue_type],
                }
            )
    for issue_type in ("punch", "ncr"):
        out.append(
            {
                "key": f"audit-internal-{issue_type}",
                "name": f"Internal audit finding ({'punch' if issue_type == 'punch' else 'NCR'})",
                "issue_type": issue_type,
                "category": "audit",
                "fields": [
                    field("audit_reference", "Audit reference", required=True),
                    field("clause", "Standard / procedure clause"),
                    *(PUNCH_COMMON if issue_type == "punch" else NCR_COMMON),
                ],
                **AUDIT_FLAGS,
                **({"default_punch_category": "C"} if issue_type == "punch" else {"default_severity": "minor"}),
            }
        )
    out.append(
        {
            "key": DOCUMENTATION_TEMPLATE_KEY,
            "name": "Documentation NCR",
            "issue_type": "ncr",
            "category": DOCUMENTATION_CATEGORY,
            "fields": list(NCR_COMMON),
            **DOCUMENTATION_FLAGS,
        }
    )
    return out


async def ensure_library(db: AsyncSession) -> None:
    """Seed the library once (idempotent). Flushes; the caller commits."""
    seeded = select(IssueCategory.id).where(IssueCategory.project_id.is_(None)).limit(1)
    if await db.scalar(seeded) is not None:
        return
    await db.execute(text("SELECT pg_advisory_xact_lock(4711003)"))
    if await db.scalar(seeded) is not None:
        return
    for order, (key, label, project_level) in enumerate(CATEGORIES):
        db.add(IssueCategory(key=key, label=label, sort_order=order, allows_project_level=project_level, pack_key="system"))
    for spec in library():
        spec = dict(spec)
        template = IssueTemplate(
            key=spec.pop("key"),
            name=spec["name"],
            issue_type=spec.pop("issue_type"),
            category=spec.pop("category"),
            pack_key="system",
        )
        db.add(template)
        await db.flush()
        db.add(
            IssueTemplateRevision(
                template_id=template.id,
                number=1,
                status=RevisionStatus.PUBLISHED.value,
                published_at=datetime.now(UTC),
                **spec,
            )
        )
        db.add(IssueDefaultTemplate(category=template.category, issue_type=template.issue_type, template_id=template.id))
    await db.flush()
