"""Threaded comments on any record, with @mentions and resolution.

Comments name their record by ``entity_type`` and ``entity_id`` and carry the record's ``project_id``,
which decides who may read them. The frontend's ``<Comments entityType entityId projectId />`` is the
whole UI. ``@username`` notifies that user; a reply notifies everyone already in the thread.
"""
