from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import ProjectStatus

Code = Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9._-]+$", examples=["P-24017"])]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$", examples=["AUD"])]


class ProjectCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: Annotated[str, Field(min_length=1, max_length=200)]
    client_name: Annotated[str | None, Field(max_length=200)] = None
    location: Annotated[str | None, Field(max_length=200)] = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    currency: Currency = "AUD"
    client_team_id: int | None = None


class ProjectUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    client_name: Annotated[str | None, Field(max_length=200)] = None
    location: Annotated[str | None, Field(max_length=200)] = None
    description: str | None = None
    status: ProjectStatus | None = None
    currency: Currency | None = None
    client_team_id: int | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    client_name: str | None
    location: str | None
    description: str | None
    status: ProjectStatus
    currency: str
    client_team_id: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
