"""The registries modules plug their reporting into: datasets, KPIs and importers.

A module registers from a ``reporting.py`` in its package; ``ensure_loaded()`` imports that file for
every module enabled at startup, so a module switched off by ``MODULES_DISABLED`` registers nothing.
Modules switched off at runtime (globally or for one project) are filtered out by ``available_*``.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging import get_logger
from ..modules.loader import enabled_modules
from ..modules.state import is_enabled

logger = get_logger()

ColumnType = Literal["text", "number", "money", "date", "bool"]
RowsFn = Callable[[AsyncSession, int | None, dict[str, Any]], Awaitable[list[dict[str, Any]]]]
KpiFn = Callable[[AsyncSession, int], Awaitable[float | int | None]]


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: ColumnType = "text"
    aggregatable: bool | None = None
    """Whether sum/avg make sense. Defaults to True for number and money columns."""

    @property
    def summable(self) -> bool:
        return self.aggregatable if self.aggregatable is not None else self.type in ("number", "money")


@dataclass(frozen=True)
class Dataset:
    """A module's records as one table.

    ``rows(db, project_id, filters)`` returns dicts keyed by column key. ``project_id`` is the project
    asked for (always set when ``project_scoped``); ``filters`` are the caller's filters, which the
    provider may use to narrow its query. The hub re-applies them to the rows afterwards, so a
    provider can ignore them. A row carrying a ``project_id`` key is only shown to people who may
    read that project.
    """

    name: str
    module: str
    title: str
    columns: list[Column]
    rows: RowsFn
    project_scoped: bool = True
    permission: str = ""
    description: str = ""

    def column(self, key: str) -> Column | None:
        return next((c for c in self.columns if c.key == key), None)


Thresholds = tuple[float, float]


@dataclass(frozen=True)
class Kpi:
    """One project figure. ``thresholds=(target, limit)``: with ``good="up"`` a value at or above
    ``target`` is good and one below ``limit`` is bad; with ``good="down"`` a value at or below
    ``target`` is good and one above ``limit`` is bad; anything between is a warning."""

    key: str
    module: str
    label: str
    fn: KpiFn
    unit: str = ""
    """``money``, ``%``, ``count`` or a free label."""
    good: Literal["up", "down"] = "up"
    thresholds: Thresholds | None = None
    permission: str = ""
    description: str = ""
    portfolio: bool = False
    """Also show this KPI as a column of the portfolio table."""

    def status(self, value: float | int | None) -> str:
        if value is None or self.thresholds is None:
            return "neutral"
        target, limit = self.thresholds
        if self.good == "up":
            return "good" if value >= target else "bad" if value < limit else "warning"
        return "good" if value <= target else "bad" if value > limit else "warning"


@dataclass(frozen=True)
class ImportField:
    key: str
    label: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    description: str = ""


class DataImportReport(BaseModel):
    """What an importer did (or, on a dry run, would do)."""

    dry_run: bool
    rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


ImportReport = DataImportReport


@dataclass
class ImportJob:
    """What an importer is asked to do. ``rows`` are the file's rows already mapped to field keys."""

    project_id: int | None
    rows: list[dict[str, Any]]
    dry_run: bool
    user_id: int | None
    columns: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    raw_rows: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


ApplyFn = Callable[[AsyncSession, ImportJob], Awaitable[ImportReport]]


@dataclass(frozen=True)
class Importer:
    name: str
    module: str
    title: str
    fields: list[ImportField]
    apply: ApplyFn
    project_scoped: bool = True
    permission: str = ""
    description: str = ""
    options: dict[str, list[str]] = field(default_factory=dict)
    """Choices the wizard offers, e.g. ``{"on_duplicate": ["update", "skip"]}``; first is the default."""


_datasets: dict[str, Dataset] = {}
_kpis: dict[str, Kpi] = {}
_importers: dict[str, Importer] = {}
_loaded = False


def register_dataset(dataset: Dataset) -> Dataset:
    _datasets[dataset.name] = dataset
    return dataset


def register_kpi(kpi: Kpi) -> Kpi:
    _kpis[kpi.key] = kpi
    return kpi


def register_importer(importer: Importer) -> Importer:
    _importers[importer.name] = importer
    return importer


def ensure_loaded() -> None:
    """Import ``reporting.py`` of every module enabled at startup, once."""
    global _loaded
    if _loaded:
        return
    for module in enabled_modules():
        try:
            module.submodule("reporting")
        except Exception:
            logger.exception("Reporting provider failed to load", extra={"module_name": module.manifest.name})
    _loaded = True


def _startup_enabled() -> set[str]:
    return {m.manifest.name for m in enabled_modules()}


def all_datasets() -> list[Dataset]:
    ensure_loaded()
    on = _startup_enabled()
    return [d for d in _datasets.values() if d.module in on]


def all_kpis() -> list[Kpi]:
    ensure_loaded()
    on = _startup_enabled()
    return [k for k in _kpis.values() if k.module in on]


def all_importers() -> list[Importer]:
    ensure_loaded()
    on = _startup_enabled()
    return [i for i in _importers.values() if i.module in on]


def _allowed(permission: str, held: frozenset[str]) -> bool:
    return not permission or all(p in held for p in permission.split(","))


async def _on(db: AsyncSession, module: str, project_id: int | None, cache: dict[str, bool]) -> bool:
    if module not in cache:
        cache[module] = await is_enabled(db, module, project_id)
    return cache[module]


async def available_datasets(db: AsyncSession, held: frozenset[str], project_id: int | None = None) -> list[Dataset]:
    """Datasets whose module is on (for the project, if given) and whose permission the caller holds."""
    cache: dict[str, bool] = {}
    return [d for d in all_datasets() if _allowed(d.permission, held) and await _on(db, d.module, project_id, cache)]


async def available_kpis(db: AsyncSession, held: frozenset[str], project_id: int | None = None) -> list[Kpi]:
    cache: dict[str, bool] = {}
    return [k for k in all_kpis() if _allowed(k.permission, held) and await _on(db, k.module, project_id, cache)]


async def available_importers(db: AsyncSession, held: frozenset[str], project_id: int | None = None) -> list[Importer]:
    cache: dict[str, bool] = {}
    return [i for i in all_importers() if _allowed(i.permission, held) and await _on(db, i.module, project_id, cache)]


async def find_dataset(db: AsyncSession, name: str, held: frozenset[str], project_id: int | None = None) -> Dataset | None:
    return next((d for d in await available_datasets(db, held, project_id) if d.name == name), None)


async def find_importer(db: AsyncSession, name: str, held: frozenset[str], project_id: int | None = None) -> Importer | None:
    return next((i for i in await available_importers(db, held, project_id) if i.name == name), None)


def unregister(name: str) -> None:
    """Drop a dataset, KPI or importer by name (for tests and plug-ins replaced at runtime)."""
    _datasets.pop(name, None)
    _kpis.pop(name, None)
    _importers.pop(name, None)
