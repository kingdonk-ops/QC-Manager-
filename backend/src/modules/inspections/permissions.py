from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("inspections")
class InspectionPermissionName(StrEnum):
    """KERP personas map onto these (see the module's ``__init__``)."""

    READ = "inspections.read"
    CREATE = "inspections.create"
    UPDATE = "inspections.update"
    DELETE = "inspections.delete"
    TRANSITION = "inspections.transition"
    SUBMIT = "inspections.submit"
    """Inspector: sign and submit a formal record."""
    REVIEW = "inspections.review"
    """QA reviewer (PER-06/PER-07): approve or return; record call-out outcomes."""
    APPROVE = "inspections.approve"
    """Hold authority: release hold points."""
    RESPOND = "inspections.respond"
    """Client representative (PER-15): confirm call-outs, acknowledge, attend, waive, co-sign."""
    MANAGE = "inspections.manage"
    """Project admin (PER-09) / QA lead: settings, locked template settings, competency register, delegations for others."""
