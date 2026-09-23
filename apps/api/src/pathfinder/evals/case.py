"""One eval case: the turns, what the assistant must do, where it came from.

A case is de-identified science. Its provenance names the site, the assistant,
how the case arrived and when, and never a user or a thread.
"""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator

from pathfinder.evals.redaction import assert_redacted

CaseOrigin = Literal["promoted", "cataloged-failure"]


class CaseProvenance(CamelModel):
    """Where a case came from, as data. No field addresses a person.

    A promoted case names the staging id it was curated from; that id is
    random and the queue row behind it is gone. A cataloged failure names the
    knowledge-bundle item that recorded the bug.
    """

    model_config = ConfigDict(frozen=True)

    site: str
    assistant: str
    origin: CaseOrigin
    added_at: str
    staging_id: str = ""
    reference: str = ""
    curator_note: str = ""

    @model_validator(mode="after")
    def _origin_names_its_source(self) -> CaseProvenance:
        if self.origin == "promoted" and not self.staging_id:
            msg = "a promoted case names the staging id it was curated from"
            raise ValueError(msg)
        if self.origin == "cataloged-failure":
            if not self.reference:
                msg = "a cataloged failure names the item that recorded it"
                raise ValueError(msg)
            if self.staging_id:
                msg = "a cataloged failure came from no staging row"
                raise ValueError(msg)
        return self


class ExpectedOutcome(CamelModel):
    """What a run of the case must produce. An unset field is not compared.

    ``parameters`` names, per search, the values that search must carry. A
    parameter the case does not name is not compared. A null
    ``builds_strategy`` accepts a build and a turn that builds nothing.
    ``reply_names_its_searches`` holds a built strategy's reply to the title
    of every search step, and a turn that built nothing to a question.
    """

    model_config = ConfigDict(frozen=True)

    builds_strategy: bool | None
    structure: str | None = None
    record_type: str | None = None
    step_count: int | None = None
    verified: bool | None = None
    step_ids_unchanged: bool | None = None
    parameters: dict[str, dict[str, str]] = Field(default_factory=dict)
    reply_mentions: list[str] = Field(default_factory=list)
    reply_omits: list[str] = Field(default_factory=list)
    reply_names_its_searches: bool = False
    step_titles_omit: list[str] = Field(default_factory=list)


class EvalCase(CamelModel):
    """The turns of one investigation, its expectation, and what it pins.

    The turns are driven in order on one thread, so a case can reach a state a
    first message cannot: an edit is a second message over a built strategy.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z0-9-]+$")
    turns: list[str] = Field(min_length=1)
    site_id: str
    assistant_id: str
    rationale: str = Field(min_length=1)
    expected: ExpectedOutcome
    provenance: CaseProvenance

    def assert_de_identified(self) -> bool:
        """True when no text field carries an identity pattern."""
        for text in (*self.turns, self.rationale, self.provenance.curator_note):
            assert_redacted(text)
        return True


__all__ = ["CaseOrigin", "CaseProvenance", "EvalCase", "ExpectedOutcome"]
