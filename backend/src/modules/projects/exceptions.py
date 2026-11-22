from ..common.exceptions import ResourceExistsError, ResourceNotFoundError


class ProjectNotFoundError(ResourceNotFoundError):
    public_detail = "Project not found."


class ProjectCodeTakenError(ResourceExistsError):
    public_detail = "A project with this code already exists."
