from ..common.exceptions import PermissionDeniedError


class SelfDeactivationError(PermissionDeniedError):
    public_detail = "You can't deactivate your own account."


class SuperuserProtectedError(PermissionDeniedError):
    public_detail = "Only a superuser can deactivate a superuser."
