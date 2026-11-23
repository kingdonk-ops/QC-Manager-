"""Request and response bodies of the recycle bin, the Deleted folder and the bin's retention setting."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ..common.pagination import MAX_INTEGER_ID
from ..common.schemas import EncodableText
from .constants import DEFAULT_RETENTION_DAYS, MAX_RETENTION_DAYS, MIN_RETENTION_DAYS
from .permit_schemas import TwPermitRead
from .schemas import TwItemRead


class TwTrashView(StrEnum):
    """The two separate views of deleted records."""

    BIN = "bin"
    DELETED = "deleted"


class TwDeletedFields(BaseModel):
    """What a deleted record adds to its normal reading. ``purge_on`` is set only for the recycle bin: the moment the
    scheduled purge may remove the record under the project's retention as it stands now."""

    deleted_at: datetime | None
    deleted_by_id: int | None
    deleted_kind: str | None
    purge_on: datetime | None = None


class TwDeletedItemRead(TwItemRead, TwDeletedFields):
    """A deleted item as the restore permission sees it in the bin or the Deleted folder."""


class TwDeletedPermitRead(TwPermitRead, TwDeletedFields):
    """A deleted permit as the restore permission sees it in the bin or the Deleted folder."""


class TwRetentionRead(BaseModel):
    project_id: int
    bin_retention_days: int
    default_days: int = DEFAULT_RETENTION_DAYS
    min_days: int = MIN_RETENTION_DAYS
    max_days: int = MAX_RETENTION_DAYS


class TwRetentionUpdate(EncodableText):
    """The recycle bin's retention for one project: whole days, one to sixty."""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1, le=MAX_INTEGER_ID)
    bin_retention_days: int = Field(ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)
