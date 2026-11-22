"""Helpers every business module uses for its records: reference numbers and status history.

from ...infrastructure.records import next_reference, record_transition, assert_transition

code = await next_reference(db, "RFI", project_id)          # "RFI-001"
code = await next_number(db, "rfi", project_id, fallback_prefix="RFI", values={"discipline": "ME"})
                                                             # the project's numbering scheme, else "RFI-001"
assert_transition(RFI_FLOW, rfi.status, "answered")          # 422 if not allowed
await record_transition(db, "rfi", rfi.id, rfi.status, "answered", user_id, note="...")
"""

from .history import assert_transition, history_of, record_transition
from .numbering import next_reference
from .schemes import NumberingError, link_allocation, next_number

__all__ = [
    "NumberingError",
    "assert_transition",
    "history_of",
    "link_allocation",
    "next_number",
    "next_reference",
    "record_transition",
]
