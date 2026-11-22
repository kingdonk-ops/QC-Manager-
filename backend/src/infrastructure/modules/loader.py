"""Finding, ordering and mounting the business modules.

A package under ``src/modules`` is a business module when it has a ``manifest.py`` exposing
``manifest = ModuleManifest(...)``. Packages without one (``user``, ``role``, ``tier``...) are the
platform's own features, wired in ``src/wiring``, and are ignored here.

For each enabled module, in dependency order:

* ``router.py`` -> ``router`` is mounted at ``/api/v1<manifest.prefix>``, plus any ``extra_routers``;
* ``models.py`` is imported (by the database registry, enabled or not, so migrations see every table);
* ``permissions.py`` registers through ``@register_permissions`` like any feature;
* ``tasks.py`` is imported by the Taskiq worker and scheduler;
* ``events.py`` is imported at startup, so its ``@subscribe`` handlers are live;
* ``__init__.py`` may define ``async def on_startup()`` / ``async def on_shutdown()``.
"""

import importlib
import importlib.util
import pkgutil
from dataclasses import dataclass
from functools import cache
from types import ModuleType
from typing import Any

from fastapi import APIRouter

from ..config.base import config
from ..logging import get_logger
from .manifest import ModuleManifest

logger = get_logger()

MODULES_PACKAGE = "src.modules"


class ModuleLoadError(RuntimeError):
    """A manifest is invalid or a dependency can't be satisfied."""


@dataclass(frozen=True)
class LoadedModule:
    manifest: ModuleManifest
    package: str
    enabled: bool

    def submodule(self, name: str) -> ModuleType | None:
        dotted = f"{self.package}.{name}"
        if importlib.util.find_spec(dotted) is None:
            return None
        return importlib.import_module(dotted)

    def has(self, name: str) -> bool:
        return importlib.util.find_spec(f"{self.package}.{name}") is not None


def _disabled_by_setting() -> set[str]:
    raw = config("MODULES_DISABLED", default="")
    return {name.strip() for name in str(raw).split(",") if name.strip()}


def _discover(package_name: str) -> dict[str, tuple[ModuleManifest, str]]:
    package = importlib.import_module(package_name)
    found: dict[str, tuple[ModuleManifest, str]] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if not info.ispkg:
            continue
        dotted = f"{package_name}.{info.name}"
        if importlib.util.find_spec(f"{dotted}.manifest") is None:
            continue
        manifest = getattr(importlib.import_module(f"{dotted}.manifest"), "manifest", None)
        if not isinstance(manifest, ModuleManifest):
            raise ModuleLoadError(f"{dotted}.manifest must define `manifest = ModuleManifest(...)`.")
        if manifest.name != info.name:
            raise ModuleLoadError(f"Module folder {info.name!r} declares the name {manifest.name!r}; they must match.")
        found[manifest.name] = (manifest, dotted)
    return found


def _order(found: dict[str, tuple[ModuleManifest, str]], disabled: set[str]) -> list[LoadedModule]:
    """Dependencies first. A module whose hard dependency is disabled is disabled too."""
    enabled = {name for name, (manifest, _) in found.items() if manifest.enabled and name not in disabled}

    changed = True
    while changed:
        changed = False
        for name in sorted(enabled):
            manifest = found[name][0]
            missing = [dep for dep in manifest.depends if dep not in found]
            if missing:
                raise ModuleLoadError(f"Module {name!r} depends on {missing}, which are not installed.")
            if any(dep not in enabled for dep in manifest.depends):
                logger.warning("Module disabled because a dependency is disabled", extra={"module_name": name})
                enabled.discard(name)
                changed = True

    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in ordered:
            return
        if name in visiting:
            raise ModuleLoadError(f"Module dependency cycle through {name!r}.")
        visiting.add(name)
        manifest = found[name][0]
        for dep in (*manifest.depends, *manifest.optional_depends):
            if dep in found:
                visit(dep)
        visiting.discard(name)
        ordered.append(name)

    for name in sorted(found):
        visit(name)

    return [LoadedModule(found[name][0], found[name][1], name in enabled) for name in ordered]


@cache
def installed_modules(package_name: str = MODULES_PACKAGE) -> tuple[LoadedModule, ...]:
    """Every business module, in load order, each marked enabled or not."""
    return tuple(_order(_discover(package_name), _disabled_by_setting()))


def enabled_modules() -> tuple[LoadedModule, ...]:
    return tuple(module for module in installed_modules() if module.enabled)


def mount_module_routers(target: APIRouter, throttle: list[Any]) -> None:
    """Mount every enabled module's routers onto the ``/api/v1`` router."""
    for module in enabled_modules():
        routes = module.submodule("router")
        if routes is None:
            continue
        dependencies = throttle if module.manifest.throttled else []
        router = getattr(routes, "router", None)
        if isinstance(router, APIRouter):
            target.include_router(router, prefix=module.manifest.prefix, dependencies=dependencies)
        for prefix, attribute in module.manifest.extra_routers.items():
            extra = getattr(routes, attribute, None)
            if not isinstance(extra, APIRouter):
                raise ModuleLoadError(f"{module.package}.router has no APIRouter named {attribute!r}.")
            target.include_router(extra, prefix=prefix, dependencies=dependencies)


def module_task_modules() -> tuple[str, ...]:
    """``tasks.py`` of every enabled module, for the Taskiq worker to import."""
    return tuple(f"{module.package}.tasks" for module in enabled_modules() if module.has("tasks"))


async def start_modules() -> None:
    for module in enabled_modules():
        module.submodule("events")
        hook = getattr(importlib.import_module(module.package), "on_startup", None)
        if hook is not None:
            await hook()
    logger.info("Modules loaded", extra={"modules": [m.manifest.name for m in enabled_modules()]})


async def stop_modules() -> None:
    for module in reversed(enabled_modules()):
        hook = getattr(importlib.import_module(module.package), "on_shutdown", None)
        if hook is not None:
            await hook()
