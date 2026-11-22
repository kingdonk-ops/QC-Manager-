from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("welding")
class WeldingPermissionName(StrEnum):
    READ = "welding.read"
    CREATE = "welding.create"
    UPDATE = "welding.update"
    """Record welding, repairs, PWHT, joint breakouts and make-ups."""
    DELETE = "welding.delete"
    REVIEW = "welding.review"
    """QC: visual inspection, NDE results, weld acceptance and cut-out."""
    APPROVE = "welding.approve"
    """Welding engineer / QA: approve WPSs, add PQRs, verify and suspend welder qualifications, NDE rates."""
    EXPORT = "welding.export"
