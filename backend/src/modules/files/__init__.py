"""Project documents and attachments on any record.

Attach to a record by uploading with ``entity_type`` and ``entity_id`` (e.g. ``rfi`` / 12); list
them with the same filter. The frontend's ``<Attachments entityType entityId projectId />`` does
both. Files sit in a storage backend (local disk by default, ``FILE_STORAGE_DIR``).
"""
