"""The contract a business module declares in its ``manifest.py``."""

import re
from dataclasses import dataclass, field
from enum import StrEnum

MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class ModuleCategory(StrEnum):
    CORE = "core"
    BUSINESS = "business"
    INTEGRATION = "integration"
    PORTAL = "portal"
    EXTENSION = "extension"


@dataclass(frozen=True)
class ModuleManifest:
    """What a module is, what it needs, and where its API lives.

    Attributes:
        name: Unique snake_case id. Must equal the package's folder name.
        version: The module's own semantic version.
        display_name: Shown in the UI's module list.
        description: One sentence.
        category: A packaging label, see ``ModuleCategory``.
        depends: Modules that must be loaded first; a missing one stops the app from starting.
        optional_depends: Modules used when present; loaded first if they are.
        enabled: ``False`` ships the module switched off. ``MODULES_DISABLED`` switches more off.
        route_prefix: Where ``router.py``'s ``router`` is mounted, under ``/api/v1``. Defaults to
            ``/<name>`` with underscores turned into hyphens.
        extra_routers: ``{prefix: attribute}`` for further routers ``router.py`` exports, for a module
            that owns more than one top-level path.
        throttled: Put the module's routes behind the API rate limit.
    """

    name: str
    version: str
    display_name: str
    description: str = ""
    category: ModuleCategory = ModuleCategory.BUSINESS
    depends: tuple[str, ...] = ()
    optional_depends: tuple[str, ...] = ()
    enabled: bool = True
    route_prefix: str | None = None
    extra_routers: dict[str, str] = field(default_factory=dict)
    throttled: bool = True

    def __post_init__(self) -> None:
        if not MODULE_NAME.match(self.name):
            raise ValueError(f"Module name {self.name!r} must be snake_case.")

    @property
    def prefix(self) -> str:
        return self.route_prefix or "/" + self.name.replace("_", "-")
