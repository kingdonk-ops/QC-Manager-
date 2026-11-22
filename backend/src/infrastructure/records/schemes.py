"""Project numbering schemes: token patterns, code lists and row-locked, never-reused counters.

A module opts in by calling ``next_number`` where it used to call ``next_reference``::

    code = await next_number(db, "rfi", project_id, fallback_prefix="RFI",
                             values={"discipline": "ME"}, entity=("rfi", rfi_id), user_id=me)

With no scheme for ``(project, "rfi")`` it answers exactly what ``next_reference(db, "RFI", project_id)`` would.
Revision and status are never part of a number: keep them in their own fields.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.common.exceptions import ValidationError
from .models import AllocatedNumber, NumberingCounter, NumberingScheme
from .numbering import next_reference

CODE_TOKENS: Final[dict[str, str]] = {
    "discipline": "Discipline code (ME, EL, CV ...)",
    "type": "Record or document type (DR, SP, RP ...)",
    "doc_type": "Document type (alias of type for document registers)",
    "area": "Area or zone of the site",
    "originator": "Originating organisation",
    "system": "System or subsystem",
    "unit": "Plant unit",
    "level": "Building level or deck",
    "package": "Work package",
    "role": "Role code",
}
"""Tokens whose value the caller gives, checked against the scheme's code list."""

AUTO_TOKENS: Final[dict[str, str]] = {
    "project": "The project's code",
    "year": "The four-digit year of allocation",
    "seq:N": "The sequence number, zero-padded to at least N digits (exactly one per pattern)",
}

TOKEN = re.compile(r"\{([a-z_]+)(?::(\d{1,2}))?\}")
LITERAL = re.compile(r"^[A-Za-z0-9 _./#-]*$")
CODE = re.compile(r"^[A-Za-z0-9]{1,20}$")
MAX_RETRIES: Final = 50


class NumberingError(ValidationError):
    """A pattern, a code or a value the scheme refuses. Answers 422."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems
        self.public_detail = "; ".join(problems)  # type: ignore[misc]


@dataclass
class Part:
    literal: str = ""
    token: str | None = None
    width: int = 0


@dataclass
class Parsed:
    parts: list[Part] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def code_tokens(self) -> list[str]:
        return [p.token for p in self.parts if p.token in CODE_TOKENS]


def parse_pattern(pattern: str) -> Parsed:
    """Split a pattern into literals and whitelisted tokens. Never ``str.format``: placeholders are matched, not evaluated."""
    out = Parsed()
    pos, seqs = 0, 0
    for match in TOKEN.finditer(pattern):
        literal = pattern[pos : match.start()]
        if literal:
            out.parts.append(Part(literal=literal))
        name, width = match.group(1), match.group(2)
        if name == "seq":
            seqs += 1
            out.parts.append(Part(token="seq", width=int(width or 1)))
        elif width is not None:
            out.errors.append(f"Only {{seq:N}} takes a width, not {{{name}:{width}}}")
        elif name in CODE_TOKENS or name in ("project", "year"):
            out.parts.append(Part(token=name))
        else:
            out.errors.append(f"Unknown token {{{name}}}")
        pos = match.end()
    if pos < len(pattern):
        out.parts.append(Part(literal=pattern[pos:]))
    for part in out.parts:
        if part.token is None and ("{" in part.literal or "}" in part.literal):
            out.errors.append(f"Malformed placeholder in '{part.literal}'")
        elif part.token is None and not LITERAL.match(part.literal):
            out.errors.append(f"'{part.literal}' may contain only letters, digits, spaces and - _ . / #")
    if seqs != 1:
        out.errors.append("The pattern needs exactly one {seq:N}" if seqs == 0 else "Only one {seq:N} is allowed")
    if not pattern.strip():
        out.errors.append("The pattern is empty")
    return out


def check_scheme(pattern: str, counter_scope: list[str], code_lists: dict[str, Any]) -> list[str]:
    """Everything wrong with a scheme, for saving it (an empty list: fine)."""
    parsed = parse_pattern(pattern)
    errors = list(parsed.errors)
    in_pattern = set(parsed.code_tokens)
    for token in counter_scope:
        if token not in CODE_TOKENS:
            errors.append(f"The counter can only run per a code token, not '{token}'")
        elif token not in in_pattern:
            errors.append(
                f"Counter scope token {{{token}}} must appear in the pattern, or two counters could print the same number"
            )
    for token, codes in code_lists.items():
        if token not in CODE_TOKENS:
            errors.append(f"Code list for unknown token '{token}'")
            continue
        for entry in codes or []:
            code = str(entry.get("code", "")) if isinstance(entry, dict) else str(entry)
            if not CODE.match(code):
                errors.append(f"Code '{code}' for {{{token}}} must be 1-20 letters or digits")
    return errors


def allowed_codes(code_lists: dict[str, Any], token: str) -> list[str]:
    return [str(e.get("code") if isinstance(e, dict) else e).upper() for e in code_lists.get(token) or []]


def check_values(parsed: Parsed, code_lists: dict[str, Any], values: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """The normalised (upper-case) values of the pattern's code tokens, and every problem."""
    clean: dict[str, str] = {}
    errors: list[str] = []
    for token in parsed.code_tokens:
        value = (values.get(token) or "").strip().upper()
        if not value:
            errors.append(f"{{{token}}} needs a value")
            continue
        codes = allowed_codes(code_lists, token)
        if codes and value not in codes:
            errors.append(f"'{value}' is not an allowed {{{token}}} code (allowed: {', '.join(codes[:12])})")
        elif not codes and not CODE.match(value):
            errors.append(f"{{{token}}} must be 1-20 letters or digits")
        clean[token] = value
    return clean, errors


def render(parsed: Parsed, project_code: str, values: dict[str, str], seq: int, year: int) -> str:
    out = []
    for part in parsed.parts:
        if part.token is None:
            out.append(part.literal)
        elif part.token == "seq":
            out.append(str(seq).zfill(part.width))
        elif part.token == "project":
            out.append(project_code)
        elif part.token == "year":
            out.append(str(year))
        else:
            out.append(values.get(part.token, ""))
    return "".join(out)


def scope_key(counter_scope: list[str], values: dict[str, str]) -> str:
    return "|".join(f"{t}={values.get(t, '')}" for t in sorted(counter_scope))


async def scheme_for(db: AsyncSession, project_id: int, record_kind: str) -> NumberingScheme | None:
    scheme: NumberingScheme | None = await db.scalar(
        select(NumberingScheme).where(
            NumberingScheme.project_id == project_id,
            NumberingScheme.record_kind == record_kind,
            NumberingScheme.active.is_(True),
        )
    )
    return scheme


async def _project_code(db: AsyncSession, project_id: int) -> str:
    # By table name, so the platform's records helpers don't import a business module.
    code = await db.scalar(text("SELECT code FROM projects WHERE id = :id"), {"id": project_id})
    return str(code) if code else str(project_id)


async def _locked_counter(db: AsyncSession, scheme: NumberingScheme, key: str) -> NumberingCounter:
    statement = (
        select(NumberingCounter)
        .where(NumberingCounter.scheme_id == scheme.id, NumberingCounter.scope_key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    counter = await db.scalar(statement)
    if counter is None:
        try:
            async with db.begin_nested():
                db.add(NumberingCounter(scheme_id=scheme.id, scope_key=key, last_value=max(scheme.start_value, 1) - 1))
        except IntegrityError:
            pass
        counter = await db.scalar(statement)
    assert counter is not None
    return counter


@dataclass
class Preview:
    number: str | None
    sequence: int | None
    scope_key: str
    errors: list[str]


async def preview(
    db: AsyncSession,
    project_id: int,
    pattern: str,
    *,
    counter_scope: list[str],
    code_lists: dict[str, Any],
    start_value: int = 1,
    values: dict[str, str] | None = None,
    scheme_id: int | None = None,
    year: int,
) -> Preview:
    """What the next number would be, without allocating it. Missing code values print as their token name."""
    errors = check_scheme(pattern, counter_scope, code_lists)
    parsed = parse_pattern(pattern)
    clean, value_errors = check_values(parsed, code_lists, values or {})
    errors += [e for e in value_errors if "needs a value" not in e]
    shown = {t: clean.get(t) or t.upper() for t in parsed.code_tokens}
    key = scope_key(counter_scope, shown)
    last = None
    if scheme_id is not None:
        last = await db.scalar(
            select(NumberingCounter.last_value).where(
                NumberingCounter.scheme_id == scheme_id, NumberingCounter.scope_key == key
            )
        )
    seq = max((last or 0) + 1, start_value)
    if parsed.errors:
        return Preview(None, None, key, errors)
    return Preview(render(parsed, await _project_code(db, project_id), shown, seq, year), seq, key, errors)


async def allocate(
    db: AsyncSession,
    scheme: NumberingScheme,
    values: dict[str, str] | None = None,
    *,
    entity: tuple[str, int] | None = None,
    user_id: int | None = None,
    year: int,
) -> AllocatedNumber:
    """The next number of ``scheme``, under a row lock on its counter. Commit with the record that uses it."""
    parsed = parse_pattern(scheme.pattern)
    problems = check_scheme(scheme.pattern, scheme.counter_scope, scheme.code_lists)
    clean, value_problems = check_values(parsed, scheme.code_lists, values or {})
    if problems or value_problems:
        raise NumberingError(problems + value_problems)
    counter = await _locked_counter(db, scheme, scope_key(scheme.counter_scope, clean))
    project_code = await _project_code(db, scheme.project_id)
    for _ in range(MAX_RETRIES):
        counter.last_value = max(counter.last_value + 1, scheme.start_value)
        await db.flush()  # outside the savepoint below, so a clash there never rolls the counter back
        number = render(parsed, project_code, clean, counter.last_value, year)
        allocation = AllocatedNumber(
            project_id=scheme.project_id,
            record_kind=scheme.record_kind,
            number=number,
            scheme_id=scheme.id,
            sequence=counter.last_value,
            values=clean,
            entity_type=entity[0] if entity else None,
            entity_id=entity[1] if entity else None,
            allocated_by_id=user_id,
        )
        try:
            async with db.begin_nested():
                db.add(allocation)
        except IntegrityError:
            # The string was handed out before (a scheme edit, or a start value moved back): skip it, never reuse it.
            continue
        await db.flush()
        return allocation
    raise NumberingError([f"No free number after {MAX_RETRIES} tries; check the scheme's start value"])


async def next_number(
    db: AsyncSession,
    record_kind: str,
    project_id: int,
    *,
    fallback_prefix: str,
    values: dict[str, str] | None = None,
    entity: tuple[str, int] | None = None,
    user_id: int | None = None,
    width: int = 3,
) -> str:
    """The project's scheme for ``record_kind`` if it has one, otherwise ``next_reference(fallback_prefix)``."""
    scheme = await scheme_for(db, project_id, record_kind)
    if scheme is None:
        return await next_reference(db, fallback_prefix, project_id, width=width)
    allocation = await allocate(db, scheme, values, entity=entity, user_id=user_id, year=datetime.now(UTC).year)
    return allocation.number


async def link_allocation(db: AsyncSession, project_id: int, record_kind: str, number: str, entity: tuple[str, int]) -> None:
    """Point an allocation at the record that got it, once the record has an id."""
    row = await db.scalar(
        select(AllocatedNumber).where(
            AllocatedNumber.project_id == project_id,
            AllocatedNumber.record_kind == record_kind,
            AllocatedNumber.number == number,
        )
    )
    if row is not None and row.entity_id is None:
        row.entity_type, row.entity_id = entity
