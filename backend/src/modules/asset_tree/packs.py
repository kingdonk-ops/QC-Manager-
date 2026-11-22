"""Starting packs: a breakdown template, terminology and item types, applied to a project (idempotent).

A project's levels are copies, not links: changing a pack never rewrites a project.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AssetLevel, ItemType

L = dict[str, Any]

PACKS: dict[str, dict[str, Any]] = {
    "remediation-rsw": {
        "title": "Remediation: Site / Area / Asset / RSW / Item",
        "levels": [
            {
                "key": "site",
                "label": "Site",
                "label_plural": "Sites",
                "depth": 0,
                "allowed_parent_keys": [],
                "roles": ["grouping"],
                "code_uniqueness": "per_project",
            },
            {
                "key": "area",
                "label": "Area",
                "label_plural": "Areas",
                "depth": 1,
                "allowed_parent_keys": ["site"],
                "roles": ["grouping", "inspection_anchor"],
            },
            {
                "key": "asset",
                "label": "Asset",
                "label_plural": "Assets",
                "depth": 2,
                "allowed_parent_keys": ["area", "site"],
                "roles": ["physical", "inspection_anchor", "schedule_link"],
            },
            {
                "key": "rsw",
                "label": "RSW",
                "label_plural": "RSWs",
                "depth": 3,
                "allowed_parent_keys": ["asset"],
                "roles": ["work_anchor", "inspection_anchor", "progress_unit", "schedule_link"],
                "display_code_template": "{asset} / {rsw}",
            },
        ],
    },
    "remediation-fep": {
        "title": "Remediation with activities: Site / Asset / RSW / Activity",
        "levels": [
            {
                "key": "site",
                "label": "Site",
                "label_plural": "Sites",
                "depth": 0,
                "allowed_parent_keys": [],
                "roles": ["grouping"],
                "code_uniqueness": "per_project",
            },
            {
                "key": "asset",
                "label": "Asset",
                "label_plural": "Assets",
                "depth": 1,
                "allowed_parent_keys": ["site"],
                "roles": ["physical", "inspection_anchor"],
            },
            {
                "key": "rsw",
                "label": "RSW",
                "label_plural": "RSWs",
                "depth": 2,
                "allowed_parent_keys": ["asset"],
                "roles": ["work_anchor", "inspection_anchor", "schedule_link"],
            },
            {
                "key": "activity",
                "label": "Activity",
                "label_plural": "Activities",
                "depth": 3,
                "allowed_parent_keys": ["rsw"],
                "roles": ["progress_unit"],
                "display_code_template": "{asset} / {rsw} / {activity}",
            },
        ],
    },
    "cui-line": {
        "title": "CUI: Scope / Job Package / Line",
        "levels": [
            {
                "key": "scope",
                "label": "Scope",
                "label_plural": "Scopes",
                "depth": 0,
                "allowed_parent_keys": [],
                "roles": ["grouping"],
                "code_uniqueness": "per_project",
            },
            {
                "key": "job_package",
                "label": "Job Package",
                "label_plural": "Job Packages",
                "depth": 1,
                "allowed_parent_keys": ["scope"],
                "roles": ["grouping", "schedule_link"],
            },
            {
                "key": "line",
                "label": "Line",
                "label_plural": "Lines",
                "depth": 2,
                "allowed_parent_keys": ["job_package"],
                "roles": ["physical", "work_anchor", "inspection_anchor", "progress_unit"],
                "code_uniqueness": "per_project",
            },
        ],
    },
}

ITEM_TYPES: list[L] = [
    {
        "key": "pipe_spool",
        "name": "Pipe spool",
        "field_schema": {
            "properties": {"nps": {"type": "string"}, "line_number": {"type": "string"}, "insulation_class": {"type": "string"}}
        },
    },
    {
        "key": "valve",
        "name": "Valve",
        "field_schema": {"properties": {"size": {"type": "string"}, "rating": {"type": "string"}}},
    },
    {
        "key": "vessel",
        "name": "Vessel / tank",
        "field_schema": {"properties": {"diameter_mm": {"type": "number"}, "height_mm": {"type": "number"}}},
    },
    {
        "key": "weld",
        "name": "Weld",
        "field_schema": {
            "properties": {"joint_type": {"type": "string"}, "wps": {"type": "string"}, "diameter_in": {"type": "number"}}
        },
    },
    {
        "key": "cml",
        "name": "Condition monitoring location",
        "field_schema": {
            "properties": {
                "cml_tag": {"type": "string"},
                "nominal_thickness_mm": {"type": "number"},
                "minimum_structural_thickness_mm": {"type": "number"},
                "design_corrosion_allowance_mm": {"type": "number"},
                "active_corrosion_rate_mm_yr": {"type": "number"},
                "last_measured_thickness_mm": {"type": "number"},
                "last_inspection_date": {"type": "string", "format": "date"},
            }
        },
    },
    {"key": "support", "name": "Pipe support", "field_schema": {}},
]


async def apply_pack(db: AsyncSession, project_id: int, key: str) -> dict[str, int]:
    pack = PACKS[key]
    have = set((await db.execute(select(AssetLevel.key).where(AssetLevel.project_id == project_id))).scalars())
    added_levels = 0
    for spec in pack["levels"]:
        if spec["key"] in have:
            continue
        db.add(AssetLevel(project_id=project_id, pack_key=key, **{"code_uniqueness": "per_parent", **spec}))
        added_levels += 1
    types = set((await db.execute(select(ItemType.key).where(ItemType.project_id == project_id))).scalars())
    added_types = 0
    for t in ITEM_TYPES:
        if t["key"] not in types:
            db.add(ItemType(project_id=project_id, **t))
            added_types += 1
    await db.commit()
    return {"levels_added": added_levels, "item_types_added": added_types}
