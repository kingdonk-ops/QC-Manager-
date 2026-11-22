from enum import StrEnum

from ...infrastructure.permissions import register_permissions


@register_permissions("ncr")
class NcrPermissionName(StrEnum):
    """Issues (punch and NCR). KERP personas map onto these (see the package docstring)."""

    READ = "ncr.read"
    CREATE = "ncr.create"
    UPDATE = "ncr.update"
    DELETE = "ncr.delete"
    TRANSITION = "ncr.transition"
    """Work the steps: rectify a punch, move an NCR through containment, root cause and actions."""
    EXPORT = "ncr.export"
    VERIFY = "ncr.verify"
    """Verify or reject a punch, record an NCR disposition, sign the effectiveness verification."""
    MANAGE = "ncr.manage"
    """QA authority / project admin: flag overrides, void, upgrade, raise external NCR, project templates."""
    CONFIGURE = "ncr.configure"
    """Library (every project) issue templates, categories and defaults."""
