from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, model_validator

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import CONSTRAINT_KINDS, OpenQuestion
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff


class FrameResult(CamelModel):
    """FRAME sub-agent output. The OperationalSpec is committed to agent_state
    via tools (not re-typed here); this delta is a light summary + disposition."""

    summary: str = ""
    disposition: Literal["spec_ready", "needs_user", "needs_research"] = "spec_ready"
    open_questions: list[OpenQuestion] = Field(
        default_factory=list,
        description=(
            "One entry per open slot only the user can decide, each naming "
            "the dimension its answer states and the value you recommend."
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


class EditDelta(CamelModel):
    """What an edit turn did to the strategy that already existed.

    ``preserved_step_ids`` are the steps the edit left alone: their WDK ids and
    their values are the ones the previous turn reported.
    """

    diff: SpecDiff
    disposition: Literal["applied", "needs_user"] = "applied"
    summary: str = ""
    open_questions: list[OpenQuestion] = Field(default_factory=list)
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
