from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff


class FrameResult(CamelModel):
    """FRAME sub-agent output. The OperationalSpec is committed to agent_state
    via tools (not re-typed here); this delta is a light summary + disposition."""

    summary: str = ""
    disposition: Literal["spec_ready", "needs_user", "needs_research"] = "spec_ready"
    open_questions: list[str] = Field(default_factory=list)
    changes: list[CriterionChange] = Field(
        default_factory=list,
        description=(
            "One entry per criterion the workspace already held, stating "
            "whether the pass kept, changed or dropped it. Empty when the "
            "workspace was empty."
        ),
    )


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
    open_questions: list[str] = Field(default_factory=list)
    description: str = ""
    operations_applied: int = 0
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
