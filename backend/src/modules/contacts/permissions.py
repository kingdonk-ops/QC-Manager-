from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("contacts")
class ContactPermissionName(StrEnum):
    READ = "contacts.read"
    CREATE = "contacts.create"
    UPDATE = "contacts.update"
    DELETE = "contacts.delete"
    IMPORT = "contacts.import"
