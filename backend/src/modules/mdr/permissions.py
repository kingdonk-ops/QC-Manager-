from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("mdr")
class MdrPermissionName(StrEnum):
    READ = "mdr.read"
    CREATE = "mdr.create"
    UPDATE = "mdr.update"
    DELETE = "mdr.delete"
    SUBMIT = "mdr.submit"
    """Compile drafts and issue revisions (document controller, QA/QC lead)."""
    SIGN = "mdr.sign"
    """Sign an issued revision for the contractor (QA/QC manager)."""
    ACCEPT = "mdr.accept"
    """Record the client's acceptance or rejection of a review revision (client portal users, or staff
    recording the client's transmittal reply)."""
