from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("coatings")
class CoatingPermissionName(StrEnum):
    READ = "coatings.read"
    CREATE = "coatings.create"
    """Create coating systems and jobs."""
    UPDATE = "coatings.update"
    """Edit systems and jobs; record environmental and DFT readings and batch numbers."""
    REVIEW = "coatings.review"
    """Release (pass) or fail a hold point (coating inspector)."""
    DELETE = "coatings.delete"
