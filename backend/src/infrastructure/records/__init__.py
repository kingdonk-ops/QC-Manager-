"""Helpers every business module uses for its records: reference numbers and status history.

from ...infrastructure.records import next_reference, record_transition, assert_transition

code = await next_reference(db, "RFI", project_id)          # "RFI-001"
assert_transition(RFI_FLOW, rfi.status, "answered")          # 422 if not allowed
await record_transition(db, "rfi", rfi.id, rfi.status, "answered", user_id, note="...")
"""

from .history import assert_transition, history_of, record_transition
from .numbering import next_reference

__all__ = ["assert_transition", "history_of", "next_reference", "record_transition"]
