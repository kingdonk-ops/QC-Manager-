from ..common.exceptions import ResourceExistsError, ResourceNotFoundError


class WorkPackageNotFoundError(ResourceNotFoundError):
    public_detail = "Work package not found."


class WorkPackageCodeTakenError(ResourceExistsError):
    public_detail = "This project already has a work package with that code."


class SnapshotNotFoundError(ResourceNotFoundError):
    public_detail = "Snapshot not found."
