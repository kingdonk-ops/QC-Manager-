"""P6 name grammar, aliases and eligibility: deterministic rules, no database.

A grammar is a regular expression with named groups. Groups named after a breakdown level key (``site``,
``asset``, ``rsw``, ...) address that level; ``asset`` also means "the level with the physical role",
``anchor_code`` the work-anchor level and ``activity_type`` a progress-unit level below the work anchor.
``suffix`` and ``window`` follow the rule's ``params``: by default a suffix (``512-21``) is part of the
anchor's code (a different RSW) and a window (``512 Online`` / ``512 Shut``) is the same RSW in another work
window, recorded on the link (KERP TD-076).
"""

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_GRAMMAR = (
    r"^(?P<asset>.+?) / (?P<activity_type>[^/]+?) / (?P<anchor_code>\d+(?:\.\d+)?)"
    r"(?:-(?P<suffix>\d+))?(?: (?P<window>Online|Shut))?$"
)
DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "kind": "grammar",
        "name": "<asset> / <activity type> / <RSW>",
        "pattern": DEFAULT_GRAMMAR,
        "source": "name",
        "params": {"suffix": "separate", "window": "same"},
        "sort_order": 10,
    },
    {
        "kind": "eligibility",
        "name": "Milestones never expect work",
        "params": {"field": "task_type", "op": "in", "values": ["TT_Mile", "TT_FinMile"]},
        "sort_order": 10,
    },
    {
        "kind": "eligibility",
        "name": "Provisional sums and custom activities",
        "params": {"field": "activity_type", "op": "in", "values": ["Prov Sums", "Custom"]},
        "sort_order": 20,
    },
    {"kind": "alias", "name": "SCA-Dism", "pattern": "SCA-Dism", "params": {"to": "SCA Dism"}, "sort_order": 10},
    {"kind": "alias", "name": "Prov.Sums", "pattern": "Prov.Sums", "params": {"to": "Prov Sums"}, "sort_order": 20},
]
SOURCES = ("name", "code", "wbs")
FIELDS = ("task_type", "activity_type", "name", "code", "wbs", "status_code")
OPS = ("equals", "in", "contains", "matches")


class GrammarError(ValueError):
    pass


def norm(value: str | None) -> str:
    """Upper case, whitespace collapsed, ``-`` and space equivalent: how codes are compared."""
    return re.sub(r"[\s\-]+", " ", (value or "").strip()).upper()


def compile_pattern(pattern: str) -> re.Pattern[str]:
    if len(pattern) > 1000:
        raise GrammarError("Patterns are limited to 1000 characters.")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise GrammarError(f"That pattern isn't a valid regular expression: {exc}") from exc
    if not compiled.groupindex:
        raise GrammarError("A grammar needs at least one named group, e.g. (?P<asset>...).")
    return compiled


@dataclass
class Grammar:
    id: int | None
    name: str
    pattern: re.Pattern[str]
    source: str = "name"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Eligibility:
    id: int | None
    name: str
    field: str
    op: str
    values: list[str]


@dataclass
class RuleSet:
    grammars: list[Grammar] = field(default_factory=list)
    eligibility: list[Eligibility] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    """``norm(found) -> replacement``."""

    def alias(self, value: str) -> str:
        return self.aliases.get(norm(value), value)


@dataclass
class Parsed:
    groups: dict[str, str] | None
    rule: str | None = None
    rule_id: int | None = None
    window: str | None = None


def build(rows: list[Any]) -> RuleSet:
    """From ``P6Rule`` rows (or anything with the same attributes); disabled rules are skipped."""
    rules = RuleSet()
    for r in sorted(rows, key=lambda x: (x.sort_order, x.id or 0)):
        if not r.enabled:
            continue
        if r.kind == "grammar":
            try:
                rules.grammars.append(Grammar(r.id, r.name, compile_pattern(r.pattern), r.source, dict(r.params or {})))
            except GrammarError:
                continue
        elif r.kind == "eligibility":
            p = r.params or {}
            values = p.get("values") or []
            rules.eligibility.append(
                Eligibility(r.id, r.name, p.get("field", "name"), p.get("op", "equals"), [str(v) for v in values])
            )
        elif r.kind == "alias" and (r.params or {}).get("to"):
            rules.aliases[norm(r.pattern)] = str(r.params["to"])
    return rules


def source_text(row: dict[str, Any], source: str) -> str:
    if source == "code":
        return row.get("p6_id") or ""
    if source == "wbs":
        return row.get("wbs_path") or ""
    return row.get("name") or ""


def parse(row: dict[str, Any], rules: RuleSet) -> Parsed:
    """The first grammar that matches, with aliases applied and suffix/window resolved into codes."""
    for g in rules.grammars:
        m = g.pattern.search(source_text(row, g.source).strip())
        if not m:
            continue
        groups = {k: rules.alias(v.strip()) for k, v in m.groupdict().items() if v is not None and v.strip()}
        window = groups.pop("window", None)
        suffix = groups.pop("suffix", None)
        if "anchor_code" in groups:
            if suffix and g.params.get("suffix", "separate") == "separate":
                groups["anchor_code"] = f"{groups['anchor_code']}-{suffix}"
            if window and g.params.get("window", "same") == "separate":
                groups["anchor_code"] = f"{groups['anchor_code']} {window}"
                window = None
        return Parsed(groups, g.name, g.id, window)
    return Parsed(None)


def _value(row: dict[str, Any], parsed: Parsed, name: str) -> str:
    if name == "activity_type":
        return (parsed.groups or {}).get("activity_type", "")
    if name == "code":
        return row.get("p6_id") or ""
    if name == "wbs":
        return row.get("wbs_path") or ""
    return str(row.get(name) or "")


def _hits(rule: Eligibility, value: str) -> bool:
    if rule.op == "equals":
        return norm(value) == norm(rule.values[0]) if rule.values else False
    if rule.op == "in":
        return norm(value) in {norm(v) for v in rule.values}
    if rule.op == "contains":
        return any(norm(v) in norm(value) for v in rule.values if v)
    if rule.op == "matches":
        for v in rule.values:
            try:
                if re.search(v, value):
                    return True
            except re.error:
                continue
    return False


def eligible(row: dict[str, Any], parsed: Parsed, rules: RuleSet) -> tuple[bool, str | None]:
    """``(False, rule name)`` when an eligibility rule takes the activity out of scope."""
    for rule in rules.eligibility:
        if _hits(rule, _value(row, parsed, rule.field)):
            return False, rule.name
    return True, None
