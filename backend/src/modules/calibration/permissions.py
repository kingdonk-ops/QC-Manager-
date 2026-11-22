from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("calibration")
class CalibrationPermissionName(StrEnum):
    READ = "calibration.read"
    CREATE = "calibration.create"
    UPDATE = "calibration.update"
    DELETE = "calibration.delete"
    UPLOAD = "calibration.upload"
    """Record a calibration certificate."""
    TRANSITION = "calibration.transition"
    """Send for calibration, quarantine, take out of or return to service."""
    EXPORT = "calibration.export"
