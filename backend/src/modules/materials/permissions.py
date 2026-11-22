from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("materials")
class MaterialsPermissionName(StrEnum):
    READ = "materials.read"
    CREATE = "materials.create"
    """Receive material, add heats, issue to work."""
    UPDATE = "materials.update"
    DELETE = "materials.delete"
    UPLOAD = "materials.upload"
    """Add mill certificates."""
    REVIEW = "materials.review"
    """QC: inspect receipts, record PMI, quarantine material."""
    APPROVE = "materials.approve"
    """QA reviewer: verify certificates, release or reject held material."""
    EXPORT = "materials.export"
