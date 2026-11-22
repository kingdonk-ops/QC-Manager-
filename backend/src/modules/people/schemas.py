from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PersonRole(BaseModel):
    id: int
    name: str
    entra_app_role: str | None = Field(None, description="Set when Entra grants this role; it can't be changed here")


class PersonTeam(BaseModel):
    id: int
    name: str
    role: str
    entra_managed: bool


class Person(BaseModel):
    id: int
    name: str
    username: str
    email: str
    account_type: Literal["staff", "external"]
    sign_in_method: Literal["entra", "password"]
    is_superuser: bool
    active: bool
    activated: bool = Field(description="Has a usable sign-in: Entra, or a password set from the invitation")
    roles: list[PersonRole] = Field(default_factory=list)
    teams: list[PersonTeam] = Field(default_factory=list)
    created_at: datetime | None = None


class RoleOption(BaseModel):
    id: int
    name: str
    description: str | None
    entra_app_role: str | None
