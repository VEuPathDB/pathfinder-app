"""The parameter sweep: a durable, approval-gated search of a built step's settings."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict, Field, field_validator
from pydantic_ai import RunContext
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk

from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.platform.durable_worker import durable_agent_tool
from pathfinder.services.parameter_optimization.config import (
    SWEEP_BUDGET,
    SWEEP_BUDGET_MAX,
    SWEEP_BUDGET_MIN,
    SweepVariantResult,
)


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


class _SweepTrials(CamelModel):
    """The trials a finished sweep reports, each with the controls it filed."""

    model_config = ConfigDict(extra="ignore")

    variants: list[SweepVariantResult] = Field(default_factory=list)


def sweep_control_runs(
    result: dict[str, Any], *, tool_call_id: str
) -> list[ControlTestRun]:
    """One control result per setting the sweep scored."""
    runs: list[ControlTestRun] = []
    for trial in _SweepTrials.model_validate(result).variants:
        positive, negative = trial.positive, trial.negative
        if positive is None and negative is None:
            continue
        runs.append(
            ControlTestRun(
                tool_call_id=f"{tool_call_id}:{trial.variant_id}",
                origin="sweep",
                evidence=ControlTestEvidence(
                    tested_label=f"setting {trial.variant_id}",
                    positive=None
                    if positive is None
                    else ControlSetEvidence(
                        returned=positive.recovered_ids,
                        not_returned=positive.missed_ids,
                    ),
                    negative=None
                    if negative is None
                    else ControlSetEvidence(
                        returned=negative.admitted_ids,
                        not_returned=negative.excluded_ids,
                    ),
                ),
            )
        )
    return runs


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


@durable_agent_tool(PARAMETER_SWEEP)
async def optimize_search_parameters(
    ctx: RunContext[LeadDeps],
    wdk_step_id: int,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
    parameters: list[str] | None = None,
    budget: Annotated[
        int, Field(ge=SWEEP_BUDGET_MIN, le=SWEEP_BUDGET_MAX)
    ] = SWEEP_BUDGET,
) -> dict[str, Any]:
    """Try other settings for one built step and score each against the controls.

    This is what a weak control test earns: the step's search is run again
    under each point of a grid, and every trial is scored by how many known
    positives it returns and how many known negatives it lets through. The
    grid comes from the catalog's own metadata for that search, so you never
    state parameter values here; the step's current values are what every
    trial holds fixed.

    A search with nothing tunable is refused by name. Propose the sweep in
    prose first - the parameters, the budget, about fifteen minutes - and
    call this only once the user says yes.

    Durable: the trials run on the worker, the turn ends while they run, and
    you are called again with the result (``variants``, ``best``,
    ``objective``, ``downloads``). Report the winning setting and its score.

    Args:
        wdk_step_id: The built step to tune, by its WDK step id. Read it from
            ``get_live_strategy_state``.
        positive_controls: Known-positive gene ids the step should return.
        negative_controls: Known-negative gene ids it should not return.
        parameters: The parameters to vary, by name. Leave it out to vary
            every tunable parameter of that step's search. The control-test
            summary names them.
        budget: The most trials to run. Each trial is one WDK call, so a
            larger budget costs proportionally more time.
    """
    del ctx, wdk_step_id, positive_controls, negative_controls, parameters, budget
    msg = "optimize_search_parameters runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)
