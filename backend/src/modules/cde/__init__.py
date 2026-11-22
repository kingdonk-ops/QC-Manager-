"""Common Data Environment aligned with ISO 19650.

Information containers move WIP -> Shared -> Published -> Archived with suitability codes
(S0; S1-S4; A1-An, CR). Revisions run P01, P02, ... while WIP or Shared and C01, C02, ... once
Published; each revision is one file in ``files`` (entity_type ``cde_document``, kept off the
project's document list so its state rules apply). Names are built and checked against the
project's naming convention. Sharing can require a task-team check (``cde.review``) and publishing
always needs a ``cde.approve`` holder other than the requester.

Who sees what: WIP is visible to its author and task-team reviewers; Shared, Published and
Archived to everyone with ``cde.read`` on the project; external portal users (those who see the
project only through its client team) see Published containers only.
"""
