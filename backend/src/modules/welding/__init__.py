"""Welding & NDE (from KERP's ``wps`` module).

A weld is an ``asset_items`` row of type ``weld``; ``welding_welds`` holds its weld data. Rules:

- **Qualification blocking.** Recording welding or a repair needs an approved WPS whose range covers the
  weld, and each welder active with a valid qualification for that WPS (or its process) on the day:
  not expired, continuity within the project's window (default 183 days), position / thickness /
  diameter / material group covered. Every weld logs continuity for its welders.
- **NDE sampling.** Each weld carries ``nde_required`` (percent per method, from its category's rates in
  the project settings). Lots are per welder and percentage; ``GET /sampling`` proposes the welds that
  fill each lot's shortfall, and ``POST /nde-requests/`` batches them. 100 % methods are added when the
  weld is recorded.
- **Progressive examination.** A rejected sample adds two more welds of the same welder (tier 1); a
  rejection there adds two more per rejection (tier 2); a rejection at tier 2 adds every remaining weld
  of the welder (tier 3).
- **Repairs.** R1, R2 (limit per project) by the same or new qualified welders; each rejected method is
  re-examined. Past the limit the weld is cut out; its replacement is a new weld (``replaces_weld_id``).
- **Acceptance** needs visual accepted, PWHT when required, every examination of the current repair
  accepted and, when ``materials`` is on, every heat issued to the weld item with a verified certificate.
- **Bolted joints** record each breakout and make-up per joint (TD-590); a make-up passes the
  ``calibration`` gate for the tools used.
"""
