"""Append to and verify the audit ledger.

Every entry stores ``prev_hash`` (the hash of the entry before it; 64 zeros for the first) and
``hash = sha256(b"qcm-audit-ledger\\n" + canonical_json(body))`` where ``body`` holds ``v``, ``seq``,
``created_at`` (UTC, microseconds), ``actor_id``, ``action``, ``entity_type``, ``entity_id``,
``project_id``, ``summary``, ``before``, ``after`` and ``prev_hash``. Canonical JSON: sorted keys,
no whitespace, UTF-8. Values are normalised before they are stored (decimals, dates and floats
become strings), so what is read back hashes the same.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditEntry

HASH_VERSION: Final = 1
HASH_DOMAIN: Final = b"qcm-audit-ledger\n"
GENESIS_HASH: Final = "0" * 64
LOCK_KEY: Final = int.from_bytes(hashlib.sha256(b"qcm-audit-ledger").digest()[:8], "big", signed=True)
VERIFY_BATCH: Final = 1000


def plain(value: Any) -> Any:
    """``value`` as JSON that survives a database round trip unchanged."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, Enum):
        return plain(value.value)
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float | Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        return sorted((plain(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    return str(value)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _utc_iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat(timespec="microseconds")


def compute_hash(entry: AuditEntry) -> str:
    body = {
        "v": HASH_VERSION,
        "seq": entry.seq,
        "created_at": _utc_iso(entry.created_at),
        "actor_id": entry.actor_id,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "project_id": entry.project_id,
        "summary": entry.summary,
        "before": entry.before,
        "after": entry.after,
        "prev_hash": entry.prev_hash,
    }
    return hashlib.sha256(HASH_DOMAIN + canonical_json(body)).hexdigest()


def changes(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only the keys whose values differ, for a compact before/after summary."""
    keys = [k for k in {**before, **after} if plain(before.get(k)) != plain(after.get(k))]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


async def record_audit(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    *,
    actor_id: int | None = None,
    project_id: int | None = None,
    summary: str | None = None,
    before: Any = None,
    after: Any = None,
) -> AuditEntry:
    """Append an entry in the caller's transaction (it commits or rolls back with the change it records).

    ``action`` is ``<module>.<entity>.<verb>`` (``mdr.revision.signed``). Keep ``before``/``after`` to a
    summary of what changed (``changes(old, new)`` helps), not whole records.
    """
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
    tail = (await db.execute(select(AuditEntry.seq, AuditEntry.hash).order_by(AuditEntry.seq.desc()).limit(1))).first()
    entry = AuditEntry(
        seq=(tail[0] + 1) if tail else 1,
        created_at=datetime.now(UTC),
        actor_id=actor_id,
        action=action[:80],
        entity_type=entity_type[:40],
        entity_id=None if entity_id is None else str(entity_id)[:80],
        project_id=project_id,
        summary=plain(summary),
        before=plain(before),
        after=plain(after),
        prev_hash=tail[1] if tail else GENESIS_HASH,
        hash="",
    )
    entry.hash = compute_hash(entry)
    db.add(entry)
    await db.flush()
    return entry


@dataclass(frozen=True)
class ChainReport:
    ok: bool
    length: int
    head_hash: str
    first_broken_seq: int | None = None
    problem: str | None = None


def _problem(entry: AuditEntry, expected_seq: int, previous_hash: str) -> str | None:
    if entry.seq != expected_seq:
        return f"expected seq {expected_seq} (an entry is missing or out of order)"
    if entry.prev_hash != previous_hash:
        return "prev_hash does not match the previous entry's hash"
    if compute_hash(entry) != entry.hash:
        return "hash does not match the entry's content (the entry was changed)"
    return None


async def verify_chain(db: AsyncSession) -> ChainReport:
    """Walk the chain from the first entry and report the first broken link.

    Detects an edited entry, a removed or inserted entry and a broken ``prev_hash`` link. Removal of
    the newest entries is not detectable without anchoring the head hash outside the database.
    """
    previous_hash, expected, length, last_seq = GENESIS_HASH, 1, 0, 0
    while True:
        batch = list(
            (
                await db.execute(
                    select(AuditEntry)
                    .where(AuditEntry.seq > last_seq)
                    .order_by(AuditEntry.seq)
                    .limit(VERIFY_BATCH)
                    .execution_options(populate_existing=True)
                )
            ).scalars()
        )
        for entry in batch:
            problem = _problem(entry, expected, previous_hash)
            if problem:
                return ChainReport(False, length, previous_hash, entry.seq, problem)
            previous_hash, expected, length = entry.hash, entry.seq + 1, length + 1
        if len(batch) < VERIFY_BATCH:
            return ChainReport(True, length, previous_hash)
        last_seq = batch[-1].seq
