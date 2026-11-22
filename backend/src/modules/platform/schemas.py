from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .access import AccessLevel


class ModuleAccessRow(BaseModel):
    module: str
    display_name: str
    level: AccessLevel | None = Field(None, description="None: follows the user's roles")
    effective: list[str] = Field(default_factory=list, description="The module's permissions the user holds now")


class AccessSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    levels: dict[str, AccessLevel | None]


class PresetApply(EncodableText):
    model_config = ConfigDict(extra="forbid")

    preset: Literal["full", "view_only", "minimal", "clear"]


class PreferenceSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]
