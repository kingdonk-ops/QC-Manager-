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
    OVERRIDE = "mdr.override"
    """Let a dossier issue past outstanding blockers with a recorded reason (manager). Full-only in the access grid, so
    the Editor and Viewer built-in roles never carry it; the migration grants it to no role, and the startup sync of the
    built-in Admin and Manager roles (every permission, minus platform administration) does carry it."""
    ACCEPT = "mdr.accept"
    """Record the client's acceptance or rejection of a review revision (client portal users, or staff
    recording the client's transmittal reply)."""
