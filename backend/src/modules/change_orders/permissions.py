from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("change_orders")
class ChangeOrderPermissionName(StrEnum):
    READ = "change_orders.read"
    CREATE = "change_orders.create"
    UPDATE = "change_orders.update"
    SUBMIT = "change_orders.submit"
    APPROVE = "change_orders.approve"
    DELETE = "change_orders.delete"
    EXPORT = "change_orders.export"
