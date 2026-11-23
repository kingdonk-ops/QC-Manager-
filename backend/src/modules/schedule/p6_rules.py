"""P6 name grammar, aliases and eligibility: deterministic rules, no database.

A grammar is a regular expression with named groups. Groups named after a breakdown level key (``site``,
``asset``, ``rsw``, ...) address that level; ``asset`` also means "the level with the physical role",
``anchor_code`` the work-anchor level and ``activity_type`` a progress-unit level below the work anchor.
``suffix`` and ``window`` follow the rule's ``params``: by default a suffix (``512-21``) is part of the
anchor's code (a different RSW) and a window (``512 Online`` / ``512 Shut``) is the same RSW in another work
window, recorded on the link (KERP TD-076).

``anchor_list`` names several work anchors in one activity (``902 - 903 - 904``). Two whole numbers joined by
the list separator are a range (``728 - 732`` is 728, 729, 730, 731 and 732), up to ``params.max_range``
codes; anything else is taken as listed. ``qualifier`` keeps a trailing note such as ``OHP``, ``Access`` or
``Props`` (part of an RSW waiting on access, a shutdown or a scaffold); it never changes which RSW is meant.

``wbs_level`` rules copy a level of the activity's WBS onto a breakdown level (for example WBS level 3 is the
Site and level 4 the Area), so the tree follows how each project's programme is structured.
"""

import re
from dataclasses import dataclass, field
from typing import Any

QUALIFIER = r"(?:(?: - |-| )(?P<qualifier>[A-Za-z][A-Za-z .]*?))?"
"""A trailing note after the code (``305 OHP``, ``305 - Access``, ``305-North``): letters, after a space or dash."""
DEFAULT_GRAMMAR = (
    r"^(?P<asset>.+?) / (?P<activity_type>[^/]+?) / (?P<anchor_code>\d+(?:\.\d+)?)"
    r"(?:-(?P<suffix>\d+))?(?: (?P<window>Online|Shut))?" + QUALIFIER + "$"
)
DEFAULT_LIST_GRAMMAR = (
    r"^(?P<asset>.+?) / (?P<activity_type>[^/]+?) / (?P<anchor_list>\d+(?:\.\d+)?(?: - \d+(?:\.\d+)?)+)"
    r"(?: (?P<window>Online|Shut))?" + QUALIFIER + "$"
)
LIST_SEPARATOR = " - "
MAX_RANGE = 50
LEVEL_VALUES = ("name", "code")
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
        "kind": "grammar",
        "name": "<asset> / <activity type> / <RSW> - <RSW> (list or range)",
        "pattern": DEFAULT_LIST_GRAMMAR,
        "source": "name",
        "params": {"window": "same", "list_separator": LIST_SEPARATOR, "max_range": MAX_RANGE},
        "sort_order": 20,
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
    {"kind": "alias", "name": "SCA-Erect", "pattern": "SCA-Erect", "params": {"to": "SCA Erect"}, "sort_order": 30},
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
class WbsLevel:
    id: int | None
    name: str
    depth: int
    """1 = the first WBS level under the project node."""
    level: str
    value: str = "name"


@dataclass
class RuleSet:
    grammars: list[Grammar] = field(default_factory=list)
    eligibility: list[Eligibility] = field(default_factory=list)
    wbs_levels: list[WbsLevel] = field(default_factory=list)
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
    anchors: list[str] = field(default_factory=list)
    """Every work-anchor code the name addresses (one, or several for a list or range)."""
    qualifier: str | None = None


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
        elif r.kind == "wbs_level":
            p = r.params or {}
            try:
                depth = int(p.get("depth") or 0)
            except (TypeError, ValueError):
                continue
            if depth >= 1 and p.get("level"):
                value = str(p["value"]) if p.get("value") in LEVEL_VALUES else "name"
                rules.wbs_levels.append(WbsLevel(r.id, r.name, depth, str(p["level"]), value))
    return rules


def expand_list(text: str, separator: str = LIST_SEPARATOR, max_range: int = MAX_RANGE) -> list[str]:
    """``902 - 903 - 905`` → listed codes; two whole numbers ``728 - 732`` → the range 728..732.

    A range longer than ``max_range`` codes, or one that runs backwards, is taken as listed (never guessed).
    """
    parts = [p.strip() for p in text.split(separator) if p.strip()]
    out: list[str] = []
    for i, part in enumerate(parts):
        if part not in out:
            out.append(part)
        if i + 1 < len(parts):
            a, b = part, parts[i + 1]
            if a.isdigit() and b.isdigit() and 0 < int(b) - int(a) < max_range:
                width = len(a) if a.startswith("0") else 0
                for n in range(int(a) + 1, int(b)):
                    code = str(n).zfill(width)
                    if code not in out:
                        out.append(code)
    return out


def wbs_values(row: dict[str, Any], rules: RuleSet) -> dict[str, str]:
    """Breakdown level → value taken from the activity's WBS by the ``wbs_level`` rules."""
    chain = row.get("wbs_chain") or []
    out: dict[str, str] = {}
    for w in rules.wbs_levels:
        if w.depth <= len(chain):
            node = chain[w.depth - 1] or {}
            value = str(node.get(w.value) or node.get("name") or node.get("code") or "").strip()
            if value:
                out.setdefault(w.level, value[:120])
    return out


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
        qualifier = groups.pop("qualifier", None)
        anchors: list[str] = []
        listed = groups.pop("anchor_list", None)
        if listed:
            try:
                max_range = int(g.params.get("max_range") or MAX_RANGE)
            except (TypeError, ValueError):
                max_range = MAX_RANGE
            anchors = expand_list(listed, str(g.params.get("list_separator") or LIST_SEPARATOR), max_range)
            groups["anchor_code"] = anchors[0]
        if "anchor_code" in groups:
            if suffix and g.params.get("suffix", "separate") == "separate":
                groups["anchor_code"] = f"{groups['anchor_code']}-{suffix}"
            if window and g.params.get("window", "same") == "separate":
                anchors = [f"{a} {window}" for a in anchors]
                groups["anchor_code"] = f"{groups['anchor_code']} {window}"
                window = None
            if not anchors:
                anchors = [groups["anchor_code"]]
        for level, value in wbs_values(row, rules).items():
            groups.setdefault(level, value)
        return Parsed(groups, g.name, g.id, window, anchors, qualifier)
    return Parsed(None)


def groups_for(parsed: Parsed) -> list[dict[str, str]]:
    """One set of groups per work anchor the name addresses."""
    if parsed.groups is None:
        return []
    if len(parsed.anchors) <= 1:
        return [parsed.groups]
    return [{**parsed.groups, "anchor_code": a} for a in parsed.anchors]


def link_info(parsed: Parsed) -> dict[str, Any]:
    """What a link keeps of the parse: the groups, the qualifier note and the other anchors of a list."""
    info: dict[str, Any] = dict(parsed.groups or {})
    if parsed.qualifier:
        info["qualifier"] = parsed.qualifier
    if len(parsed.anchors) > 1:
        info["anchors"] = parsed.anchors
    return info


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
