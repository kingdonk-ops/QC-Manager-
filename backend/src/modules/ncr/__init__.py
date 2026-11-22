"""Non-conformance reports: root cause, disposition, corrective and preventive actions, cost of quality.

Other modules raise an NCR through ``service.create_ncr`` (inspections does, for a failed checklist item),
passing ``source="inspection"`` and the inspection and item ids so the report links back to its origin.
"""
