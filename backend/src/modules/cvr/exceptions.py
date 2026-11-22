from ..common.exceptions import ResourceExistsError, ResourceNotFoundError


class CostHeadNotFoundError(ResourceNotFoundError):
    public_detail = "Cost head not found."


class CostHeadCodeTakenError(ResourceExistsError):
    public_detail = "This project already has a cost head with that code."
