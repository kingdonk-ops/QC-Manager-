from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText
from ..files.schemas import FileRead
from .constants import Decision, SubmittalType

Title = Annotated[str, Field(min_length=1, max_length=300)]
SpecSection = Annotated[str | None, Field(max_length=50)]
EntityType = Annotated[str | None, Field(max_length=40, pattern=r"^[a-z][a-z0-9_]*$")]
Comment = Annotated[str | None, Field(max_length=5000)]


class SubmittalWorkflowStep(EncodableText):
    """One step: a single reviewer, or several deciding in parallel.

    Several reviewers on a step that isn't ``parallel`` review one after another.
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(max_length=100)] = ""
    reviewer_ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1, max_length=20)
    parallel: bool = False


Workflow = Annotated[list[SubmittalWorkflowStep], Field(max_length=20)]


class SubmittalCreate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    title: Title
    description: str | None = None
    type: SubmittalType = SubmittalType.SHOP_DRAWING
    spec_section: SpecSection = None
    entity_type: EntityType = None
    entity_id: int | None = Field(None, ge=1)
    submitted_by_contact_id: int | None = Field(None, ge=1)
    submitted_by_user_id: int | None = Field(None, ge=1, description="Defaults to the creator")
    required_by: date | None = None
    workflow: Workflow = Field(default_factory=list)


class SubmittalUpdate(EncodableText):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: str | None = None
    type: SubmittalType | None = None
    spec_section: SpecSection = None
    entity_type: EntityType = None
    entity_id: int | None = Field(None, ge=1)
    submitted_by_contact_id: int | None = Field(None, ge=1)
    submitted_by_user_id: int | None = Field(None, ge=1)
    required_by: date | None = None
    workflow: Workflow | None = Field(None, description="Only while the current revision is a draft")


class SubmittalReviewDecision(EncodableText):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    comment: Comment = None


class SubmittalRevise(EncodableText):
    model_config = ConfigDict(extra="forbid")

    note: Comment = None
    file_ids: list[Annotated[int, Field(ge=1)]] = Field(
        default_factory=list,
        max_length=50,
        description="Files already uploaded (unfiled, or on this submittal) to attach to the new revision",
    )
    workflow: Workflow | None = Field(None, description="Replace the workflow for the new cycle")
    submit: bool = Field(True, description="Submit the new revision at once; otherwise it starts as a draft")


class SubmittalNote(EncodableText):
    model_config = ConfigDict(extra="forbid")

    note: Comment = None


class SubmittalReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step: int
    step_name: str
    parallel: bool
    reviewer_id: int | None
    reviewer_name: str | None = None
    state: str
    decision: str | None
    comment: str | None
    opened_at: datetime | None
    decided_at: datetime | None


class SubmittalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    title: str
    description: str | None
    type: str
    spec_section: str | None
    entity_type: str | None
    entity_id: int | None
    submitted_by_contact_id: int | None
    submitted_by_user_id: int | None
    submitted_by_name: str | None = None
    required_by: date | None
    status: str
    revision: int
    revision_letter: str = "A"
    current_revision_id: int | None = None
    workflow: list[SubmittalWorkflowStep]
    current_reviewers: list[str] = Field(default_factory=list)
    current_reviewer_ids: list[int] = Field(default_factory=list)
    submitted_at: datetime | None = None
    days_outstanding: int | None = None
    overdue: bool = False
    created_by_id: int | None
    created_at: datetime | None = None


class SubmittalDetail(SubmittalRead):
    reviews: list[SubmittalReviewRead] = Field(default_factory=list, description="The current revision's workflow")
    my_open_review_id: int | None = None


class SubmittalRevisionRead(BaseModel):
    id: int
    number: int
    letter: str
    note: str | None
    outcome: str | None
    submitted_at: datetime | None
    completed_at: datetime | None
    created_at: datetime | None
    reviews: list[SubmittalReviewRead]
    files: list[FileRead]


class SubmittalReviewerOption(BaseModel):
    id: int
    name: str
    email: str


class SubmittalHistoryRead(BaseModel):
    from_status: str | None
    to_status: str
    changed_by_id: int | None
    changed_by_name: str | None = None
    note: str | None
    changed_at: str | None
