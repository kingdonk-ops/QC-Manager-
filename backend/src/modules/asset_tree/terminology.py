"""Terminology: what a project calls its levels and domain nouns, with plural forms.

Keys:

* ``level.<key>``: a breakdown level (``level.rsw`` → RSW / RSWs). Defaults to the level's label and plural.
* ``role.<role>``: the first level carrying a role (``role.work_anchor`` → RSW in a remediation project,
  Line in a CUI one), so screens can say "work anchor" in the project's words.
* ``noun.<name>``: domain nouns (items, collections, job packs...).

A project override (``AssetTerm``) wins over the level, which wins over the built-in default. Labels are
English only for now; per-locale packs come with a second locale.
"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import Role
from .models import AssetLevel, AssetTerm

Forms = dict[str, str]

DEFAULT_TERMS: dict[str, Forms] = {
    "noun.node": {"one": "Node", "other": "Nodes"},
    "noun.item": {"one": "Item", "other": "Items"},
    "noun.item_type": {"one": "Item type", "other": "Item types"},
    "noun.identifier": {"one": "Tag", "other": "Tags"},
    "noun.collection": {"one": "Collection", "other": "Collections"},
    "noun.job_pack": {"one": "Job pack", "other": "Job packs"},
    "noun.shutdown_window": {"one": "Shutdown window", "other": "Shutdown windows"},
    "noun.test_pack": {"one": "Test pack", "other": "Test packs"},
    "noun.work_plan": {"one": "Work plan", "other": "Work plans"},
    **{
        f"role.{r.value}": {
            "one": r.value.replace("_", " ").capitalize(),
            "other": r.value.replace("_", " ").capitalize() + "s",
        }
        for r in Role
    },
}


async def resolved(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
    """Every term the project uses, with where its words came from (``default``, ``level`` or ``project``)."""
    terms: dict[str, dict[str, Any]] = {k: {**v, "source": "default"} for k, v in DEFAULT_TERMS.items()}
    levels = (
        await db.execute(
            select(AssetLevel).where(AssetLevel.project_id == project_id).order_by(AssetLevel.depth, AssetLevel.id)
        )
    ).scalars()
    role_level: dict[str, str] = {}
    for level in levels:
        terms[f"level.{level.key}"] = {"one": level.label, "other": level.label_plural, "source": "level"}
        for role in level.roles:
            role_level.setdefault(f"role.{role}", f"level.{level.key}")
    overrides = {t.key: t for t in (await db.execute(select(AssetTerm).where(AssetTerm.project_id == project_id))).scalars()}
    for t in overrides.values():
        terms[t.key] = {"one": t.one, "other": t.other, "source": "project"}
    for role_key, level_key in role_level.items():
        if role_key not in overrides:  # a role reads as its level, renamed or not
            terms[role_key] = dict(terms[level_key])
    return [{"key": k, **{f: v[f] for f in ("one", "other", "source")}} for k, v in sorted(terms.items())]


async def set_terms(db: AsyncSession, project_id: int, changes: dict[str, Forms | None]) -> None:
    """Set (or, with ``None``, clear) project overrides."""
    existing = {t.key: t for t in (await db.execute(select(AssetTerm).where(AssetTerm.project_id == project_id))).scalars()}
    for key, forms in changes.items():
        if forms is None:
            await db.execute(delete(AssetTerm).where(AssetTerm.project_id == project_id, AssetTerm.key == key))
        elif key in existing:
            existing[key].one, existing[key].other = forms["one"], forms["other"]
        else:
            db.add(AssetTerm(project_id=project_id, key=key, one=forms["one"], other=forms["other"]))
    await db.flush()


async def add_defaults(db: AsyncSession, project_id: int, terms: dict[str, Forms]) -> None:
    """A pack's terminology: added where the project has no override yet, never overwritten."""
    have = set((await db.execute(select(AssetTerm.key).where(AssetTerm.project_id == project_id))).scalars())
    for key, forms in terms.items():
        if key not in have:
            db.add(AssetTerm(project_id=project_id, key=key, one=forms["one"], other=forms["other"]))


def term(terms: dict[str, Forms], key: str, count: int = 1) -> str:
    """The word for ``key``: ``term(t, "level.rsw", 2)`` → "RSWs". Unknown keys fall back to the key's last part."""
    forms = terms.get(key)
    if not forms:
        return key.rsplit(".", 1)[-1].replace("_", " ")
    return forms["one"] if count == 1 else forms["other"]
