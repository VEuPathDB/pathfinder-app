from __future__ import annotations

from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, model_validator

from pathfinder.ai.graph.state import OmittedFromInput, VerificationDigest
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import CONSTRAINT_KINDS
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    SlotQuestion,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff
from pathfinder.domain.strategy.step_words import AddedSearch

_ADDED_SEARCHES = (
    "The search each step this turn added runs, by its name on the site, the "
    "words it stands for, and why it was chosen over the searches the catalog "
    "answered. The reply names every one and gives its reason beside the name."
)


class FrameResult(CamelModel):
    """FRAME sub-agent output. The OperationalSpec is committed to agent_state
    via tools (not re-typed here); this delta is a light summary + disposition."""

    summary: str = ""
    disposition: Literal["spec_ready", "needs_user", "needs_research"] = "spec_ready"
    open_questions: list[SlotQuestion] = Field(
        default_factory=list,
        description=(
            "One entry per open slot only the user can decide, each naming "
            "the dimension its answer states, the value you recommend, the "
            "`criterion_id` and `param_name` of the slot, and in `options` up "
            "to 8 values the sheet you read offers for it: its facets or its "
            "vocabulary. Each option sets that parameter to its value. The "
            "Lead asks it on the question card with those options."
        ),
    )
    unstated: list[str] = Field(
        default_factory=list,
        description=(
            "Each requirement of the request that no search on this site "
            "states, in the researcher's own words. Nothing is bound for it."
        ),
    )
    changes: list[CriterionChange] = Field(
        default_factory=list,
        description=(
            "One entry per criterion the workspace already held, stating "
            "whether the pass kept, changed or dropped it. Empty when the "
            "workspace was empty."
        ),
    )
    # The open questions as the question card asks them. The dispatch sets it
    # from the recorded questions, so FRAME's schema omits it.
    card_questions: Annotated[list[CardQuestion], OmittedFromInput] = Field(
        default_factory=list
    )

    def questions(self, spec: OperationalSpec | None = None) -> list[OpenQuestion]:
        """The open questions, each option typed by what answering it binds.

        ``spec`` holds the criteria the questions set, which name each
        parameter and hold the counts measured at the offered values. A
        question whose offered values bind one value offers no choice, so it
        is not asked.
        """
        by_id = {c.id: c for c in spec.criteria} if spec is not None else {}
        noun = counted_noun(None if spec is None else spec.record_type)
        return [
            q.typed(by_id.get(q.criterion_id), noun=noun)
            for q in self.open_questions
            if q.offers_a_choice(by_id.get(q.criterion_id))
        ]

    @model_validator(mode="after")
    def _every_asked_question_decides_something(self) -> FrameResult:
        """A pass that stops on the user asks for a value on a named dimension.

        A question that names neither a dimension nor a recommended value
        leaves the next turn nothing to bind and nothing to read an answer
        against.
        """
        if self.disposition != "needs_user":
            return self
        undecided = [
            q.question for q in self.open_questions if not q.decides_a_dimension
        ]
        if undecided:
            msg = (
                f"These open questions decide nothing: {undecided}. Give each "
                f"one the `dimension` its open parameter states, one of "
                f"{CONSTRAINT_KINDS}, and the `recommended_value` you would "
                f"use if the user does not answer."
            )
            raise ValueError(msg)
        return self


class ExecuteDelta(CamelModel):
    """Declarative BUILD output. No LLM ran; this is the build result."""

    outcome: BuildOutcome
    added_searches: list[AddedSearch] = Field(
        default_factory=list, description=_ADDED_SEARCHES
    )


class EditDelta(CamelModel):
    """What an edit turn did to the strategy that already existed.

    ``preserved_step_ids`` are the steps the edit left alone: their WDK ids and
    their values are the ones the previous turn reported.
    """

    diff: SpecDiff
    # ``unbound``: every framing pass of the edit was refused, and the summary
    # says why; nothing was applied.
    disposition: Literal["applied", "needs_user", "unbound"] = "applied"
    summary: str = ""
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    # The open questions as the question card asks them, option by option.
    card_questions: list[CardQuestion] = Field(default_factory=list)
    description: str = ""
    operations_applied: int = 0
    added_step_ids: list[str] = Field(
        default_factory=list,
        description=(
            "The criteria this edit built a step for, which is what the diff "
            "counts as added: the diff is measured against the spec the "
            "strategy answers to, so a criterion framed on an earlier turn and "
            "built here reads as added in both."
        ),
    )
    added_searches: list[AddedSearch] = Field(
        default_factory=list, description=_ADDED_SEARCHES
    )
    preserved_step_ids: list[str] = Field(default_factory=list)
    dropped_step_ids: list[str] = Field(default_factory=list)
    failed_step_ids: list[str] = Field(default_factory=list)


class RecoveryDelta(CamelModel):
    """Execution-recovery sub-agent output (only invoked when build fails).

    The agent emits only the light fields; the resulting ``BuildOutcome`` is
    re-derived by re-syncing the strategy (the agent re-typing the full outcome
    object fumbled ``counts`` and caused a think-loop)."""

    actions_taken: list[str] = Field(default_factory=list)
    follow_up_needed: bool = False


class VerificationDelta(CamelModel):
    """Verification sub-agent output."""

    digest: VerificationDigest


class VerificationStopped(CamelModel):
    """A check that ended before it returned a digest. It records no verdict
    and no evidence card, so the strategy stays unverified."""

    stop: PhaseStop | None
    summary: str
