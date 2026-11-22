"""Submittals: shop drawings, product data and samples sent for review through a multi-stage workflow.

Each submittal carries revisions (Rev A, Rev B, ...). A revision is reviewed through ordered steps;
a step is one reviewer, or a parallel group that completes when every member decides. The outcome
is the most severe decision of the last completed step, and a ``revise_and_resubmit`` or
``rejected`` decision ends the review at once. Files for a revision are stored with ``files`` under
``entity_type="submittal_revision"`` and the revision's id.
"""
