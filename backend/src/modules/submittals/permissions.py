from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("submittals")
class SubmittalPermissionName(StrEnum):
    READ = "submittals.read"
    CREATE = "submittals.create"
    UPDATE = "submittals.update"
    DELETE = "submittals.delete"
    SUBMIT = "submittals.submit"
    REVIEW = "submittals.review"
    EXPORT = "submittals.export"
