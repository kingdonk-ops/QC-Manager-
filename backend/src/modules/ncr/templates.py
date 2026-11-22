"""Issue templates: field definitions, answer validation, revisions, and the library -> project layers.

A template's type and category are fixed; its revisions carry the fields and flag defaults. Revisions are
``draft`` (editable) or ``published`` (frozen); issues pin the published revision they were raised on.
Library rows (``project_id`` NULL) are copied into a project, never overlaid: a project copy keeps
``derived_from_id`` and hides its library source from that project's lists.
"""

import re
from datetime import UTC, date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..files.models import StoredFile
from .constants import STEPS, FieldType, IssueType, RevisionStatus
from .models import IssueCategory, IssueDefaultTemplate, IssueTemplate, IssueTemplateRevision
from .seed import ensure_library

FLAG_KEYS = (
    "default_origin",
    "default_visibility",
    "default_mdr_effect",
    "completion_effect",
    "default_severity",
    "default_punch_category",
    "separate_close",
)


class IssueRuleError(ValidationError):
    """A 422 whose message the caller sees."""

    public_detail = "That change breaks the issue's rules."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_detail = message  # type: ignore[misc]


class TemplateNotFound(ResourceNotFoundError):
    public_detail = "Issue template not found."


class FieldDef(BaseModel):
    """One template field. ``step`` says when it is filled; it is read-only once that step is completed."""

    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    type: FieldType = FieldType.TEXT
    step: Annotated[str, Field(max_length=30)] = "raise"
    required: bool = False
    options: Annotated[list[Annotated[str, Field(min_length=1, max_length=100)]], Field(max_length=100)] = []
    help: Annotated[str | None, Field(max_length=500)] = None
    unit: Annotated[str | None, Field(max_length=20)] = None
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _options(self) -> "FieldDef":
        if self.type in (FieldType.SELECT, FieldType.MULTISELECT) and not self.options:
            raise ValueError(f"{self.key}: a {self.type.value} field needs options")
        return self


def check_fields(issue_type: str, fields: list[Any]) -> list[dict[str, Any]]:
    """Validate field definitions for a type; returns them as plain dicts (422 on any problem)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    steps = STEPS[issue_type]
    for raw in fields:
        try:
            f = FieldDef.model_validate(raw.model_dump() if isinstance(raw, BaseModel) else raw)
        except Exception as exc:
            raise IssueRuleError(f"Invalid field: {exc}") from exc
        if f.key in seen:
            raise IssueRuleError(f"Field key {f.key!r} is used twice.")
        if f.step not in steps:
            raise IssueRuleError(f"Field {f.key!r}: step must be one of {', '.join(steps)} for a {issue_type}.")
        seen.add(f.key)
        out.append(f.model_dump(mode="json", exclude_none=True))
    return out


def json_schema(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """The JSON Schema of a revision's ``answers`` (every field optional here; ``required`` is per step)."""
    props: dict[str, Any] = {}
    for f in fields:
        kind = f["type"]
        schema: dict[str, Any] = {"title": f["label"], "x-step": f["step"]}
        if kind in ("text", "textarea"):
            schema |= {"type": "string", "maxLength": 20000}
        elif kind == "number":
            schema |= {"type": "number"}
            if f.get("min") is not None:
                schema["minimum"] = f["min"]
            if f.get("max") is not None:
                schema["maximum"] = f["max"]
        elif kind == "date":
            schema |= {"type": "string", "format": "date"}
        elif kind == "select":
            schema |= {"type": "string", "enum": f["options"]}
        elif kind == "multiselect":
            schema |= {"type": "array", "items": {"type": "string", "enum": f["options"]}, "uniqueItems": True}
        elif kind == "checkbox":
            schema |= {"type": "boolean"}
        elif kind == "photo":
            schema |= {"type": "array", "items": {"type": "integer"}, "description": "File ids"}
        if f.get("required"):
            schema["x-required-at-step"] = f["step"]
        props[f["key"]] = schema
    return {"type": "object", "properties": props, "additionalProperties": False}


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value is False


async def check_answers(
    db: AsyncSession,
    project_id: int,
    fields: list[dict[str, Any]],
    answers: dict[str, Any],
) -> dict[str, Any]:
    """Validate answers against field definitions; returns normalised answers (422 on any problem)."""
    by_key = {f["key"]: f for f in fields}
    out: dict[str, Any] = {}
    photo_ids: set[int] = set()
    for key, value in answers.items():
        f = by_key.get(key)
        if f is None:
            raise IssueRuleError(f"{key!r} is not a field of this template.")
        if value is None:
            out[key] = None
            continue
        kind, label = f["type"], f["label"]
        if kind in ("text", "textarea"):
            if not isinstance(value, str) or len(value) > 20000:
                raise IssueRuleError(f"{label}: text expected.")
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise IssueRuleError(f"{label}: a number expected.")
            if (f.get("min") is not None and value < f["min"]) or (f.get("max") is not None and value > f["max"]):
                raise IssueRuleError(f"{label}: out of range.")
        elif kind == "date":
            try:
                date.fromisoformat(str(value))
            except ValueError as exc:
                raise IssueRuleError(f"{label}: a date (YYYY-MM-DD) expected.") from exc
        elif kind == "select":
            if value not in f["options"]:
                raise IssueRuleError(f"{label}: choose one of the options.")
        elif kind == "multiselect":
            if not isinstance(value, list) or any(v not in f["options"] for v in value):
                raise IssueRuleError(f"{label}: choose from the options.")
        elif kind == "checkbox":
            if not isinstance(value, bool):
                raise IssueRuleError(f"{label}: true or false expected.")
        elif kind == "photo":
            if not isinstance(value, list) or any(isinstance(v, bool) or not isinstance(v, int) for v in value):
                raise IssueRuleError(f"{label}: a list of file ids expected.")
            photo_ids |= set(value)
        out[key] = value
    if photo_ids:
        found = set(
            (
                await db.execute(select(StoredFile.id).where(StoredFile.id.in_(photo_ids), StoredFile.project_id == project_id))
            ).scalars()
        )
        if photo_ids - found:
            raise IssueRuleError("A photo is not a file of this project.")
    return out


def missing_required(fields: list[dict[str, Any]], answers: dict[str, Any], steps: set[str]) -> list[str]:
    return [f["label"] for f in fields if f.get("required") and f["step"] in steps and _empty(answers.get(f["key"]))]


# --- layers ------------------------------------------------------------------------------------------


def _layer(project_id: int | None, column: Any) -> Any:
    return column.is_(None) if project_id is None else (column.is_(None) | (column == project_id))


async def categories_for(db: AsyncSession, project_id: int | None) -> list[dict[str, Any]]:
    """Library categories, with the project's own rows replacing those of the same key."""
    await ensure_library(db)
    rows = (
        await db.execute(
            select(IssueCategory).where(_layer(project_id, IssueCategory.project_id)).order_by(IssueCategory.sort_order)
        )
    ).scalars()
    merged: dict[str, IssueCategory] = {}
    for row in sorted(rows, key=lambda r: r.project_id is not None):
        merged[row.key] = row
    return sorted(
        (
            {
                "key": c.key,
                "label": c.label,
                "is_active": c.is_active,
                "sort_order": c.sort_order,
                "allows_project_level": c.allows_project_level,
                "layer": "library" if c.project_id is None else "project",
            }
            for c in merged.values()
        ),
        key=lambda c: (c["sort_order"], c["key"]),
    )


async def category_of(db: AsyncSession, project_id: int, key: str) -> dict[str, Any]:
    for c in await categories_for(db, project_id):
        if c["key"] == key:
            return c
    raise IssueRuleError(f"Unknown issue category {key!r}.")


async def upsert_category(db: AsyncSession, project_id: int | None, key: str, values: dict[str, Any]) -> None:
    await ensure_library(db)
    row = await db.scalar(
        select(IssueCategory).where(
            IssueCategory.key == key,
            IssueCategory.project_id.is_(None) if project_id is None else IssueCategory.project_id == project_id,
        )
    )
    if row is None:
        base = next((c for c in await categories_for(db, project_id) if c["key"] == key), None)
        row = IssueCategory(
            project_id=project_id,
            key=key,
            label=(base or {}).get("label", key.replace("_", " ").capitalize()),
            sort_order=(base or {}).get("sort_order", 100),
            allows_project_level=(base or {}).get("allows_project_level", False),
        )
        db.add(row)
    for name, value in values.items():
        if value is not None:
            setattr(row, name, value)
    await db.flush()


async def templates_for(
    db: AsyncSession, project_id: int | None, issue_type: str | None = None, category: str | None = None
) -> list[IssueTemplate]:
    """Library templates the project hasn't copied, plus the project's own."""
    await ensure_library(db)
    where = [_layer(project_id, IssueTemplate.project_id)]
    if issue_type:
        where.append(IssueTemplate.issue_type == issue_type)
    if category:
        where.append(IssueTemplate.category == category)
    rows = list((await db.execute(select(IssueTemplate).where(*where).order_by(IssueTemplate.name))).scalars())
    copied = {r.derived_from_id for r in rows if r.project_id is not None and r.derived_from_id}
    return [r for r in rows if r.id not in copied]


async def get_template(db: AsyncSession, template_id: int, project_id: int | None = None) -> IssueTemplate:
    """A template usable in this project (a library one or the project's own)."""
    template = await db.get(IssueTemplate, template_id)
    if template is None or (template.project_id is not None and template.project_id != project_id):
        raise TemplateNotFound(str(template_id))
    return template


async def published(db: AsyncSession, template_id: int) -> IssueTemplateRevision | None:
    rev: IssueTemplateRevision | None = await db.scalar(
        select(IssueTemplateRevision)
        .where(IssueTemplateRevision.template_id == template_id, IssueTemplateRevision.status == RevisionStatus.PUBLISHED)
        .order_by(IssueTemplateRevision.number.desc())
        .limit(1)
    )
    return rev


async def draft_of(db: AsyncSession, template_id: int) -> IssueTemplateRevision | None:
    rev: IssueTemplateRevision | None = await db.scalar(
        select(IssueTemplateRevision).where(
            IssueTemplateRevision.template_id == template_id, IssueTemplateRevision.status == RevisionStatus.DRAFT
        )
    )
    return rev


async def default_template(db: AsyncSession, project_id: int, category: str, issue_type: str) -> IssueTemplate | None:
    """Project mapping, then library mapping, for the category; then the same for ``general``; then any."""
    await ensure_library(db)
    for cat in dict.fromkeys((category, "general")):
        for layer in (project_id, None):
            mapping = await db.scalar(
                select(IssueDefaultTemplate).where(
                    IssueDefaultTemplate.project_id.is_(None) if layer is None else IssueDefaultTemplate.project_id == layer,
                    IssueDefaultTemplate.category == cat,
                    IssueDefaultTemplate.issue_type == issue_type,
                )
            )
            if mapping and mapping.template_id:
                template = await db.get(IssueTemplate, mapping.template_id)
                if template and template.is_active:
                    # a library default the project has copied resolves to the copy
                    copy = await db.scalar(
                        select(IssueTemplate).where(
                            IssueTemplate.project_id == project_id, IssueTemplate.derived_from_id == template.id
                        )
                    )
                    return copy or template
        found = await templates_for(db, project_id, issue_type, cat)
        if found:
            return found[0]
    return None


async def defaults_for(db: AsyncSession, project_id: int | None) -> list[dict[str, Any]]:
    await ensure_library(db)
    rows = (await db.execute(select(IssueDefaultTemplate).where(_layer(project_id, IssueDefaultTemplate.project_id)))).scalars()
    merged: dict[tuple[str, str], IssueDefaultTemplate] = {}
    for row in sorted(rows, key=lambda r: r.project_id is not None):
        merged[(row.category, row.issue_type)] = row
    return [
        {
            "category": c,
            "issue_type": t,
            "template_id": row.template_id,
            "layer": "library" if row.project_id is None else "project",
        }
        for (c, t), row in sorted(merged.items())
    ]


async def set_default(db: AsyncSession, project_id: int | None, category: str, issue_type: str, template_id: int) -> None:
    template = await get_template(db, template_id, project_id)
    if template.issue_type != issue_type:
        raise IssueRuleError("That template is of the other issue type.")
    row = await db.scalar(
        select(IssueDefaultTemplate).where(
            IssueDefaultTemplate.project_id.is_(None) if project_id is None else IssueDefaultTemplate.project_id == project_id,
            IssueDefaultTemplate.category == category,
            IssueDefaultTemplate.issue_type == issue_type,
        )
    )
    if row is None:
        db.add(IssueDefaultTemplate(project_id=project_id, category=category, issue_type=issue_type, template_id=template_id))
    else:
        row.template_id = template_id
    await db.flush()


# --- authoring ---------------------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "template"


async def create_template(
    db: AsyncSession,
    *,
    project_id: int | None,
    name: str,
    issue_type: IssueType | str,
    category: str,
    user_id: int,
    fields: list[Any] | None = None,
    flags: dict[str, Any] | None = None,
) -> IssueTemplate:
    """A new template with draft revision 1. Without fields/flags, it starts from the ``general`` template of the type."""
    issue_type = str(issue_type)
    if project_id is not None:
        await category_of(db, project_id, category)
    elif category not in {c["key"] for c in await categories_for(db, None)}:
        raise IssueRuleError(f"Unknown issue category {category!r}.")
    preset = None
    general = await default_template(db, project_id, "general", issue_type) if project_id else None
    if general is None:
        general = await db.scalar(
            select(IssueTemplate).where(
                IssueTemplate.project_id.is_(None),
                IssueTemplate.category == "general",
                IssueTemplate.issue_type == issue_type,
            )
        )
    if general is not None:
        preset = await published(db, general.id)
    key = _slug(f"{category}-{issue_type}-{name}")
    taken = await db.scalar(
        select(func.count()).where(
            IssueTemplate.key.like(f"{key}%"),
            IssueTemplate.project_id.is_(None) if project_id is None else IssueTemplate.project_id == project_id,
        )
    )
    template = IssueTemplate(
        project_id=project_id,
        key=f"{key}-{taken + 1}" if taken else key,
        name=name,
        issue_type=issue_type,
        category=category,
        created_by_id=user_id,
    )
    db.add(template)
    await db.flush()
    base = {k: getattr(preset, k) for k in FLAG_KEYS} if preset else {}
    base |= {k: v for k, v in (flags or {}).items() if k in FLAG_KEYS and v is not None}
    db.add(
        IssueTemplateRevision(
            template_id=template.id,
            number=1,
            name=name,
            fields=check_fields(issue_type, fields if fields is not None else (preset.fields if preset else [])),
            created_by_id=user_id,
            **base,
        )
    )
    await db.flush()
    return template


async def save_draft(db: AsyncSession, template: IssueTemplate, values: dict[str, Any], user_id: int) -> IssueTemplateRevision:
    """Edit the draft, starting one from the latest published revision when there is none."""
    draft = await draft_of(db, template.id)
    if draft is None:
        current = await published(db, template.id)
        number = (
            await db.scalar(
                select(func.max(IssueTemplateRevision.number)).where(IssueTemplateRevision.template_id == template.id)
            )
            or 0
        )
        draft = IssueTemplateRevision(
            template_id=template.id,
            number=number + 1,
            name=current.name if current else template.name,
            fields=list(current.fields) if current else [],
            created_by_id=user_id,
            **({k: getattr(current, k) for k in FLAG_KEYS} if current else {}),
        )
        db.add(draft)
    if values.get("fields") is not None:
        draft.fields = check_fields(template.issue_type, values["fields"])
    for key in (*FLAG_KEYS, "name", "notes"):
        if values.get(key) is not None:
            setattr(draft, key, values[key].value if hasattr(values[key], "value") else values[key])
    if template.issue_type == IssueType.NCR:
        draft.default_punch_category = None
        draft.separate_close = False
    await db.flush()
    return draft


async def publish(db: AsyncSession, template: IssueTemplate, user_id: int) -> IssueTemplateRevision:
    draft = await draft_of(db, template.id)
    if draft is None:
        raise IssueRuleError("There is no draft to publish.")
    draft.status = RevisionStatus.PUBLISHED.value
    draft.published_at = datetime.now(UTC)
    draft.published_by_id = user_id
    if draft.name:
        template.name = draft.name
    await db.flush()
    return draft


async def copy_to_project(db: AsyncSession, template: IssueTemplate, project_id: int, user_id: int) -> IssueTemplate:
    """The project's copy of a library template (made once), with the latest published revision as its revision 1."""
    if template.project_id is not None:
        return template
    existing = await db.scalar(
        select(IssueTemplate).where(IssueTemplate.project_id == project_id, IssueTemplate.derived_from_id == template.id)
    )
    if existing:
        return existing
    source = await published(db, template.id)
    copy = IssueTemplate(
        project_id=project_id,
        key=template.key,
        name=template.name,
        issue_type=template.issue_type,
        category=template.category,
        derived_from_id=template.id,
        created_by_id=user_id,
    )
    db.add(copy)
    await db.flush()
    if source:
        db.add(
            IssueTemplateRevision(
                template_id=copy.id,
                number=1,
                status=RevisionStatus.PUBLISHED.value,
                name=source.name,
                fields=list(source.fields),
                created_by_id=user_id,
                published_by_id=user_id,
                published_at=datetime.now(UTC),
                notes=f"Copied from library revision {source.number}",
                **{k: getattr(source, k) for k in FLAG_KEYS},
            )
        )
        await db.flush()
    return copy


def revision_read(rev: IssueTemplateRevision) -> dict[str, Any]:
    return {
        "id": rev.id,
        "template_id": rev.template_id,
        "number": rev.number,
        "status": rev.status,
        "name": rev.name,
        "fields": rev.fields,
        "json_schema": json_schema(rev.fields),
        "notes": rev.notes,
        "published_at": rev.published_at.isoformat() if rev.published_at else None,
        **{k: getattr(rev, k) for k in FLAG_KEYS},
    }


async def template_read(db: AsyncSession, template: IssueTemplate, *, revisions: bool = False) -> dict[str, Any]:
    pub = await published(db, template.id)
    draft = await draft_of(db, template.id)
    out: dict[str, Any] = {
        "id": template.id,
        "project_id": template.project_id,
        "key": template.key,
        "name": template.name,
        "issue_type": template.issue_type,
        "category": template.category,
        "is_active": template.is_active,
        "derived_from_id": template.derived_from_id,
        "layer": "library" if template.project_id is None else "project",
        "published": revision_read(pub) if pub else None,
        "draft": revision_read(draft) if draft else None,
        "revisions": [],
    }
    if revisions:
        rows = (
            await db.execute(
                select(IssueTemplateRevision)
                .where(IssueTemplateRevision.template_id == template.id)
                .order_by(IssueTemplateRevision.number)
            )
        ).scalars()
        out["revisions"] = [{"id": r.id, "number": r.number, "status": r.status, "published_at": r.published_at} for r in rows]
    return out
