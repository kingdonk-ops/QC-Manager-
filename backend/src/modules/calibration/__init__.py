"""Calibration: the measuring and test equipment register, certificates, due reminders and a hard gate.

**The gate.** Any module that stores a reading taken with an instrument calls, in the same transaction
and before it saves::

    from ..calibration.service import assert_calibrated

    if await is_enabled(db, "calibration", project_id):          # list "calibration" in optional_depends
        await assert_calibrated(db, equipment_ids, reading_date, project_id=project_id)

It raises ``CalibrationGateError`` (a ``ValidationError``, so the API answers 422) whose message names
every piece that is quarantined, out of service, away for calibration, never calibrated, or whose
certificate had expired on ``reading_date``. Welding's bolted-joint make-up uses it for torque
wrenches and tensioning tools; materials uses it for PMI analysers.

**Inspections** should do the same when an inspection is completed: store the equipment ids used on
the inspection (or per numeric checklist item, beside ``reading``) and call ``assert_calibrated`` with
``inspected_date`` before scoring. Pickers list ``GET /api/v1/calibration/available?project_id=&on=``,
and a form can preview the gate with ``POST /api/v1/calibration/gate``.
"""
