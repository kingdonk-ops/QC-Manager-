from ..common.exceptions import ResourceExistsError


class EmailTakenError(ResourceExistsError):
    public_detail = "An account with this email already exists."
