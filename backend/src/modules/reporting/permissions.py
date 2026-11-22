from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("reporting")
class ReportingPermissionName(StrEnum):
    READ = "reporting.read"
    """Dashboards, the portfolio, pivots and templates. Each dataset and KPI also needs its module's permission."""
    EXPORT = "reporting.export"
    """Generate a report file from a template, and export a pivot."""
    CREATE = "reporting.create"
    """Create templates and schedules."""
    UPDATE = "reporting.update"
    """Change templates and schedules, and send a scheduled report now."""
    DELETE = "reporting.delete"
