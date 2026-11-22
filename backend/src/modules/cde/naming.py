"""Building and checking container names against a naming convention. Pure functions."""

from typing import Any

from .constants import CHARSETS

CHARSET_WORDS = {"alnum": "letters and digits", "alpha": "letters", "numeric": "digits"}


def _describe(field: dict[str, Any]) -> str:
    return f"{field['label']} ({field['key']})"


def check_value(field: dict[str, Any], value: str, separator: str) -> str | None:
    """Why ``value`` doesn't fit ``field``, or ``None`` when it does."""
    where = _describe(field)
    if not value:
        return f"{where} is required"
    if separator in value:
        return f"{where}: '{value}' must not contain the separator '{separator}'"
    codes = [c["code"].upper() for c in field.get("codes") or []]
    if codes:
        if value not in codes:
            shown = ", ".join(codes[:12]) + (", ..." if len(codes) > 12 else "")
            return f"{where}: '{value}' is not an allowed code (allowed: {shown})"
        return None
    low, high = int(field.get("min_length", 1)), int(field.get("max_length", 20))
    if not low <= len(value) <= high:
        size = f"{low}" if low == high else f"{low} to {high}"
        return f"{where}: '{value}' must be {size} characters long"
    charset = field.get("charset", "alnum")
    if not (value.isascii() and CHARSETS[charset](value)):
        return f"{where}: '{value}' may contain only {CHARSET_WORDS[charset]}"
    return None


def compose(convention: dict[str, Any], values: dict[str, str]) -> tuple[str, dict[str, str], list[str]]:
    """The name, the normalised (upper-case) values, and every problem found."""
    separator = convention["separator"]
    fields = convention["fields"]
    known = {f["key"] for f in fields}
    clean = {k: (v or "").strip().upper() for k, v in values.items()}
    errors = [
        f"Unknown field '{k}' (the convention has: {', '.join(f['key'] for f in fields)})" for k in clean if k not in known
    ]
    for field in fields:
        problem = check_value(field, clean.get(field["key"], ""), separator)
        if problem:
            errors.append(problem)
    ordered = {f["key"]: clean.get(f["key"], "") for f in fields}
    return separator.join(ordered.values()), ordered, errors


def parse(convention: dict[str, Any], name: str) -> tuple[str, dict[str, str], list[str]]:
    """Split a name into its fields, then check them."""
    separator = convention["separator"]
    fields = convention["fields"]
    stem = name.strip()
    parts = stem.split(separator)
    if len(parts) != len(fields):
        expected = separator.join(f["key"].upper() for f in fields)
        return (
            stem,
            {},
            [f"'{stem}' has {len(parts)} parts separated by '{separator}' but the convention has {len(fields)}: {expected}"],
        )
    return compose(convention, {f["key"]: part for f, part in zip(fields, parts, strict=True)})


def example(convention: dict[str, Any]) -> str:
    out = []
    for field in convention["fields"]:
        codes = field.get("codes") or []
        if codes:
            out.append(codes[0]["code"].upper())
        elif field.get("charset") == "numeric":
            out.append("1".zfill(int(field.get("min_length", 1))))
        else:
            out.append("X" * int(field.get("min_length", 1)))
    separator: str = convention["separator"]
    return separator.join(out)
