"""Issues engine (KERP MOD-09): punch items and NCRs as two types of one template-driven record.

* Workflow comes from the type (``constants.FLOWS``), fields from layered, revisioned templates (``templates``).
* Other modules raise issues through ``service.create_issue`` (``service.create_ncr`` stays for callers that
  raise an NCR the old way, e.g. inspections for a failed checklist item). The MDR reads its gate through
  ``service.blocking_issues`` and its register through ``service.mdr_register``; the work-completion gate
  through ``service.completion_blockers``.

KERP personas map onto permissions as follows (grant them through roles):

=====================================  ==========================================================
PER-03/04 supervisors (rectify)        ``ncr.read``, ``ncr.create``, ``ncr.update``, ``ncr.transition``
PER-06 QA/QC lead (QA authority)       the above + ``ncr.verify``, ``ncr.manage``, ``ncr.export``
PER-07 QC inspector                    ``ncr.read``, ``ncr.create``, ``ncr.update``, ``ncr.verify``
PER-09 project admin                   ``ncr.manage`` (flags, void, upgrade, external NCR, project templates)
PER-13 tenant/library admin            ``ncr.configure`` (library templates, categories, defaults)
PER-15 client (portal, external)       ``ncr.read``, ``ncr.create``, ``ncr.verify`` (client-origin punches only)
=====================================  ==========================================================
"""
