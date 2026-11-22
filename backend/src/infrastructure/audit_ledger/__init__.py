"""The append-only, hash-chained audit ledger every module can write to.

from ...infrastructure.audit_ledger import changes, record_audit

old, new = changes({"status": n.status}, {"status": "retired"})
await record_audit(db, "asset_tree.node.retired", "asset_node", node.id, actor_id=user["id"],
                   project_id=node.project_id, summary=f"Retired {node.code}", before=old, after=new)
await db.commit()   # the entry commits with the change it records

The explorer and the chain check are the ``audit`` module (``/api/v1/audit``).
"""

from .models import APPEND_ONLY_SQL, AppendOnlyError, AuditEntry
from .service import GENESIS_HASH, ChainReport, changes, compute_hash, plain, record_audit, verify_chain

__all__ = [
    "APPEND_ONLY_SQL",
    "GENESIS_HASH",
    "AppendOnlyError",
    "AuditEntry",
    "ChainReport",
    "changes",
    "compute_hash",
    "plain",
    "record_audit",
    "verify_chain",
]
