"""Request and response bodies of the additional-signatory action and the signatory status read."""

from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import EncodableText


class AdditionalSignatory(EncodableText):
    """One more distinct person signing an ITP line over its current content."""

    model_config = ConfigDict(extra="forbid")

    accept_intent: bool = Field(False, description="The signer accepts the additional-signatory statement")


class SignatoryPerson(BaseModel):
    user_id: int
    name: str | None = None
    roles: list[str]


class SignatoryStatus(BaseModel):
    """The required count, how many distinct people have signed, who they are and whether the requirement is met."""

    inspection_id: int
    required: int
    collected: int
    met: bool
    signers: list[SignatoryPerson]
