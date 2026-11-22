"""What the registries look like over the API, and the import wizard's column guessing."""

import re
from typing import Any

from pydantic import BaseModel

from .registry import Dataset, Importer, ImportField, Kpi


class ColumnInfo(BaseModel):
    key: str
    label: str
    type: str
    aggregatable: bool


class DatasetInfo(BaseModel):
    name: str
    module: str
    title: str
    description: str
    project_scoped: bool
    columns: list[ColumnInfo]


class KpiInfo(BaseModel):
    key: str
    module: str
    label: str
    unit: str
    good: str
    thresholds: list[float] | None
    description: str
    portfolio: bool


class ImportFieldInfo(BaseModel):
    key: str
    label: str
    required: bool
    description: str


class ImporterInfo(BaseModel):
    name: str
    module: str
    title: str
    description: str
    project_scoped: bool
    fields: list[ImportFieldInfo]
    options: dict[str, list[str]]


def dataset_info(d: Dataset) -> DatasetInfo:
    return DatasetInfo(
        name=d.name,
        module=d.module,
        title=d.title,
        description=d.description,
        project_scoped=d.project_scoped,
        columns=[ColumnInfo(key=c.key, label=c.label, type=c.type, aggregatable=c.summable) for c in d.columns],
    )


def kpi_info(k: Kpi) -> KpiInfo:
    return KpiInfo(
        key=k.key,
        module=k.module,
        label=k.label,
        unit=k.unit,
        good=k.good,
        thresholds=list(k.thresholds) if k.thresholds else None,
        description=k.description,
        portfolio=k.portfolio,
    )


def importer_info(i: Importer) -> ImporterInfo:
    return ImporterInfo(
        name=i.name,
        module=i.module,
        title=i.title,
        description=i.description,
        project_scoped=i.project_scoped,
        fields=[ImportFieldInfo(key=f.key, label=f.label, required=f.required, description=f.description) for f in i.fields],
        options=i.options,
    )


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def auto_mapping(fields: list[ImportField], columns: list[str]) -> dict[str, str]:
    """Guess ``{field: column}`` from the file's headers, by key, label and aliases."""
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    by_norm = {_norm(c): c for c in columns}
    for f in fields:
        for name in (f.key.replace("_", " "), f.label, *f.aliases):
            column = by_norm.get(_norm(name))
            if column is not None and column not in taken:
                mapping[f.key] = column
                taken.add(column)
                break
    return mapping


def map_rows(rows: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [{field: row.get(column) for field, column in mapping.items()} for row in rows]
