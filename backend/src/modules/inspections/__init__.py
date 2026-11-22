"""Quality inspections, on KERP's one-engine model (TD-002).

One record table for both kinds: ``inspection`` (a checklist record) and ``itp`` (one line of an Inspection and
Test Plan applied to an anchor). Templates carry an area (``qa_itp`` anchors to the asset tree; other areas are
project-level with informational location and links), a formal flag (formal: submit → review; informal: complete
directly), an audit scope, linked issue types and frozen revisions.

Around the records: ITP instances with Hold / Witness / Review / Surveillance points per party, inspection requests
(call-outs) with notice rules and per-party delivery, a stateless ``eligibility`` check, signing with a content hash
and competency at signing, client co-sign (portal, on-device, scan), and narrow delegation of authority.

KERP personas → permissions:

- PER-06 QA/QC lead, PER-07 site QA → ``inspections.review`` (approve/return, call-out outcomes) and, for hold
  authority, ``inspections.approve`` (Hold release).
- Inspector / supervisor (PER-03, PER-04) → ``inspections.create``, ``update``, ``submit``.
- PER-15 client representative → ``inspections.read`` + ``inspections.respond`` (confirm, acknowledge, attend,
  waive, co-sign and confirm provisional co-signs), through the client portal's project visibility.
- PER-09 project admin → ``inspections.manage`` (settings, locked template settings, competency register,
  delegations for others).
"""
