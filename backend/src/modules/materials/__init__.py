"""Materials & traceability (from KERP's ``materials`` module, MOD-07).

Receipts (MRIR, linked to a procurement PO / goods receipt when that module is on) bring in **heats**
(heat, lot or batch numbers per material grade). Each heat carries mill certificates (MTC, the file in
Files) that QA verifies, PMI results (the analyser must pass the ``calibration`` gate; a rejected PMI
quarantines the heat), and quarantine **holds** (released or rejected). Material is **issued** to a
work anchor of the asset tree (directly or through an item on it), which gives traceability both ways:
``/trace/items/{id}`` and ``/trace/nodes/{id}`` (item / subtree → heats → certificates) and
``/trace/heats/{id}`` (heat → where used).

**For the MDR**, call::

    from ..materials.service import certificates_for

    rows = await certificates_for(db, await subtree_ids(db, node_id))          # verified_only=True to be strict

One row per certificate (rejected ones left out) of every heat issued to those nodes or to items on
them: certificate number and type, status, heat number, grade, product form, issuer, issue date,
``file_id`` (the PDF in Files) and the ``node_ids`` it went to. ``GET /api/v1/materials/appendix``
serves the same list.

**Client-supplied material** (TD-593): a heat with ``supplied_by = client``, still ``expected`` and
planned for a work anchor whose ``planned_start`` is before its ``expected_delivery`` (or that has no
expected date) shows as a warning on that anchor: ``readiness_warnings(db, project_id, node_ids)`` and
``GET /warnings``. Never a block.

Welding refuses to accept a weld whose item was issued a heat without a verified certificate
(``unverified_heats_for_items``).
"""
