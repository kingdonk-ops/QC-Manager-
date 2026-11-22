from enum import StrEnum

TEAM_NAME_MAX_LENGTH = 100
ENTRA_OBJECT_ID_LENGTH = 36
APP_ROLE_VALUE_MAX_LENGTH = 120


class TeamRole(StrEnum):
    """A member's role within one team. Ordered weakest first."""

    MEMBER = "member"
    LEAD = "lead"
    MANAGER = "manager"
