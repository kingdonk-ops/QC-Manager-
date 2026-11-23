from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("temporary_works")
class TemporaryWorksPermissionName(StrEnum):
    READ = "temporary_works.read"
    """Viewer: the register, items, permits, the rollup and the load-status view."""
    CREATE = "temporary_works.create"
    """Editor: create an item or a draft permit."""
    UPDATE = "temporary_works.update"
    """Editor: edit an item or a draft permit."""
    DELETE = "temporary_works.delete"
    """Editor: delete an item or a permit that is in draft (a soft delete; the record is hidden, never removed)."""
    RETURN_TO_DRAFT = "temporary_works.return_to_draft"
    """Separate from edit: send an item or a permit back to draft, with a mandatory reason that is audit-logged."""
    RESTORE = "temporary_works.restore"
    """Sees the recycle bin and the hidden Deleted folder, brings a deleted draft back, and sets the bin's retention. Held
    separately from delete, so only the people who manage deleted records can see or reverse them."""
    TRANSITION = "temporary_works.transition"
    """Editor: move an item along its guarded status flow."""
    ISSUE = "temporary_works.issue"
    """Temporary works coordinator: issue, activate and close a permit."""
    EXPORT = "temporary_works.export"
