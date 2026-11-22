from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("workface_log")
class WorkfaceLogPermissionName(StrEnum):
    READ = "workface_log.read"
    CREATE = "workface_log.create"
    UPDATE = "workface_log.update"
    DELETE = "workface_log.delete"
    SUBMIT = "workface_log.submit"
    """Lock a day's log and send it for sign-off (the crew's supervisor)."""
    REVIEW = "workface_log.review"
    """Sign off a submitted log, or return it (the superintendent)."""
    EXPORT = "workface_log.export"
