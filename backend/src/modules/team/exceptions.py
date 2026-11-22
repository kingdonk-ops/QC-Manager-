"""Team errors."""

from ..common.exceptions import PermissionDeniedError, ResourceExistsError, ResourceNotFoundError, ValidationError


class TeamNotFoundError(ResourceNotFoundError):
    public_detail = "Team not found."


class TeamExistsError(ResourceExistsError):
    public_detail = "A team with this name, or linked to this Entra group, already exists."


class MembershipNotFoundError(ResourceNotFoundError):
    public_detail = "That user is not a member of this team."


class EntraManagedTeamError(ValidationError):
    public_detail = "This team's members come from its Entra group: change the group in Entra instead."


class NotTeamLeadError(PermissionDeniedError):
    public_detail = "Only the team's leads and managers, or holders of team.manage_members, can change its members."


class RoleMappingNotFoundError(ResourceNotFoundError):
    public_detail = "No role is mapped to that Entra app role."


class GraphNotConfiguredError(ValidationError):
    public_detail = "Microsoft Graph sync is not configured: set OAUTH_ENTRA_TENANT_ID, _CLIENT_ID and _CLIENT_SECRET."
