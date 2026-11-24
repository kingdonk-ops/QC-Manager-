from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("as_built")
class AsBuiltPermissionName(StrEnum):
    READ = "as_built.read"
    CREATE = "as_built.create"
    """Editor: create a record."""
    UPDATE = "as_built.update"
    """Editor: edit a record and record a survey."""
    DELETE = "as_built.delete"
    """Manager: delete a draft or surveyed record."""
    REVIEW = "as_built.review"
    """Manager: verify a surveyed record."""
    APPROVE = "as_built.approve"
    """Manager: sign the legal-record attestation of a verified record."""
