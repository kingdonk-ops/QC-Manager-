from enum import StrEnum


class Category(StrEnum):
    ASSIGNMENT = "assignment"
    MENTION = "mention"
    STATUS = "status"
    APPROVAL = "approval"
    DUE = "due"
    SYSTEM = "system"


DEFAULTS: dict[str, tuple[bool, bool]] = {
    Category.ASSIGNMENT: (True, True),
    Category.MENTION: (True, True),
    Category.STATUS: (True, False),
    Category.APPROVAL: (True, True),
    Category.DUE: (True, True),
    Category.SYSTEM: (True, False),
}
"""(in-app, email) for a user who hasn't set a preference."""
