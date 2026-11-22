from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from .constants import ContactType

Short = Annotated[str | None, Field(max_length=200)]


class CompanyIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    type: ContactType = ContactType.OTHER
    tax_id: Annotated[str | None, Field(max_length=50)] = None
    address: str | None = None
    phone: Annotated[str | None, Field(max_length=50)] = None
    email: Short = None
    website: Short = None
    banking: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class CompanyRead(CompanyIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_count: int = 0


class ContactIn(EncodableText):
    model_config = ConfigDict(extra="forbid")

    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(max_length=100)] = ""
    company_id: int | None = None
    type: ContactType = ContactType.OTHER
    job_title: Annotated[str | None, Field(max_length=150)] = None
    email: Short = None
    phone: Annotated[str | None, Field(max_length=50)] = None
    mobile: Annotated[str | None, Field(max_length=50)] = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = None


class ProjectRole(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    role: str | None


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    full_name: str = ""
    company_id: int | None
    company_name: str | None = None
    type: str
    job_title: str | None
    email: str | None
    phone: str | None
    mobile: str | None
    tags: list[str]
    notes: str | None
    user_id: int | None
    projects: list[ProjectRole] = Field(default_factory=list)
    created_at: datetime | None = None


class ProjectLinkSet(EncodableText):
    model_config = ConfigDict(extra="forbid")

    role: Annotated[str | None, Field(max_length=150)] = None


class ImportReport(BaseModel):
    dry_run: bool
    rows: int
    created: int
    updated: int
    skipped: int
    duplicates: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
