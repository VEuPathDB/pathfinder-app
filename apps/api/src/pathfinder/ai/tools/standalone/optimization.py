"""Standalone optimization tools for pydantic-ai agents.

Provides:

- ``optimize_search_parameters`` — optimise search parameters against control
  gene lists. Durable: the real work runs on the verification worker via
  ``@durable_tool``; the call is deferred while trials run and per-trial
  progress streams back through ``task_progress``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome, durable_tool
from pydantic import ConfigDict, Field, field_validator
from pydantic_ai import RunContext
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._optimization_models import (
    OptimizationControls,
    OptimizationSettings,
    OptimizationTarget,
)

_DEFAULT_SETTINGS = OptimizationSettings()


class _SweepBest(CamelModel):
    """The winning trial's score, as the sweep reports it."""

    model_config = ConfigDict(extra="ignore")

    score: float = 0.0

    @field_validator("score", mode="before")
    @classmethod
    def _absent_is_zero(cls, value: object) -> object:
        return 0.0 if value is None else value


class _SweepOutcome(CamelModel):
    """What a finished sweep says about the settings it tried."""

    model_config = ConfigDict(extra="ignore")

    variants: list[dict[str, Any]] = Field(default_factory=list)
    best: _SweepBest = Field(default_factory=_SweepBest)
    objective: str = "score"

    @field_validator("best", mode="before")
    @classmethod
    def _no_winner_scores_zero(cls, value: object) -> object:
        return {} if value is None else value


def _sweep_chunks_from_result(
    resumed: Any,
    task_id: UUID,
    tool_call_id: str | None,
) -> list[BaseChunk]:
    del task_id
    outcome = DurableOutcome.model_validate(resumed)
    if not outcome.succeeded:
        return []
    sweep = _SweepOutcome.model_validate(outcome.result)
    return summary_chunks(
        tool_call_id,
        f"{len(sweep.variants)} settings tried, "
        f"best {sweep.objective} {sweep.best.score:.3f}",
    )


PARAMETER_SWEEP = declare_durable_tool(
    tool_name="optimize_search_parameters",
    estimated_duration_seconds=900,
    chunks_from_result=_sweep_chunks_from_result,
)


@durable_tool(PARAMETER_SWEEP)
async def optimize_search_parameters(
    ctx: RunContext[AgentDeps],
    target: OptimizationTarget,
    controls: OptimizationControls,
    settings: OptimizationSettings = _DEFAULT_SETTINGS,
) -> dict[str, Any]:
    """Optimise search parameters against positive/negative control gene lists.

    Durable. Runs up to ``settings.budget`` trials on the verification
    worker; each trial calls WDK. The turn ends while the optimiser runs, and
    you are called again with the result dict (matching
    :class:`OptimizationResult`'s ``model_dump(by_alias=True)`` shape).

    This is a long-running operation. Always confirm the plan with the user
    before calling; the verification toolset carries ``requires_approval=True``
    so the SDK emits a ``ToolApprovalRequestChunk`` first.

    Args:
        target: Target search to optimise.
        controls: Control sets for scoring.
        settings: Optimisation hyperparameters.
    """
    del ctx, target, controls, settings
    msg = "optimize_search_parameters runs on the worker via @durable_tool"
    raise NotImplementedError(msg)
