from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("change_of_scope")
class ChangeOfScopePermissionName(StrEnum):
    READ = "change_of_scope.read"
    CREATE = "change_of_scope.create"
    UPDATE = "change_of_scope.update"
    DELETE = "change_of_scope.delete"
    SUBMIT = "change_of_scope.submit"
    RESPOND = "change_of_scope.respond"
    """Record the client's acknowledgement."""
    APPROVE = "change_of_scope.approve"
    """Record the client's approval or rejection, and convert an approved card to a change order."""
    EXPORT = "change_of_scope.export"
