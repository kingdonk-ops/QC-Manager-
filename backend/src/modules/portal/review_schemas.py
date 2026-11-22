from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText

PlanKind = Literal["work_plan", "itp", "method_statement", "schedule", "drawing", "other"]
Decision = Literal["approved", "approved_with_comments", "rejected"]


class ReviewDocumentAdd(EncodableText):
    model_config = ConfigDict(extra="forbid")

    file_id: int = Field(ge=1, description="An uploaded file of the same project")
    title: Annotated[str | None, Field(max_length=300, description="The file's name by default")] = None


class PlanReviewCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    kind: PlanKind = "work_plan"
    message: Annotated[str | None, Field(max_length=10_000)] = None
    due_date: date | None = Field(None, description="The review deadline")
    client_team_id: int | None = Field(None, ge=1, description="The project's client team by default")
    documents: list[ReviewDocumentAdd] = Field(default_factory=list, max_length=100)


class PlanReviewUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    kind: PlanKind | None = None
    message: Annotated[str | None, Field(max_length=10_000)] = None
    due_date: date | None = None


class ReviewShare(EncodableText):
    model_config = ConfigDict(extra="forbid")

    note: Annotated[str | None, Field(max_length=2000)] = Field(None, description="Added to the notification")


class DocumentDecision(EncodableText):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    comment: Annotated[str | None, Field(max_length=10_000, description="Required unless approving outright")] = None


class ReviewCommentCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1, max_length=10_000)]
    document_id: int | None = Field(None, ge=1, description="Comment on one document; the whole package by default")


class ReviewDocumentRead(BaseModel):
    id: int
    file_id: int
    title: str
    file_name: str | None = None
    content_type: str | None = None
    size: int | None = None
    decision: str
    decision_comment: str | None
    decided_by_name: str | None = None
    decided_at: datetime | None


class ReviewCommentRead(BaseModel):
    id: int
    document_id: int | None
    author_id: int | None
    author_name: str | None
    from_client: bool
    body: str
    created_at: datetime | None


class PlanReviewRead(BaseModel):
    id: int
    project_id: int
    code: str
    title: str
    kind: str
    message: str | None
    client_team_id: int | None
    client_team_name: str | None = None
    due_date: date | None
    overdue: bool = False
    status: str
    outcome: str | None
    documents_total: int = 0
    documents_decided: int = 0
    shared_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime | None = None


class PlanReviewDetail(PlanReviewRead):
    documents: list[ReviewDocumentRead]
    comments: list[ReviewCommentRead]
    can_decide: bool = False
    can_manage: bool = False
