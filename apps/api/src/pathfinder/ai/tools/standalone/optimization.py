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
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk
from veupathdb.domain.strategy import record_class_of
from veupathdb_mcp.controls import ControlTargetData, ControlTestResult

from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.platform.durable_worker import durable_agent_tool
from pathfinder.services.evidence.optimization import tunable_parameters_of_search
from pathfinder.services.experiment.metrics import metrics_from_control_result
from pathfinder.services.experiment.scored_comparison import (
    ScoredComparison,
    ScoredVariant,
)
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


class _SweepTable(_SweepTrials):
    """A finished sweep as its table reads it: the search and the objective."""

    search_name: str
    objective: str


def _varied(variants: list[SweepVariantResult]) -> list[str]:
    """The parameters whose value differs between the settings."""
    names = sorted({name for variant in variants for name in variant.params})
    return [
        name
        for name in names
        if len({v.params[name].to_wire() for v in variants if name in v.params}) > 1
    ]


def _scored(variant: SweepVariantResult, label: str, search: str) -> ScoredVariant:
    if variant.status != "success":
        return ScoredVariant(label=label, search_name=search, error=variant.error)
    metrics = metrics_from_control_result(
        ControlTestResult(
            target=ControlTargetData(
                search_name=search, estimated_size=variant.estimated_size
            ),
            positive=variant.positive,
            negative=variant.negative,
        )
    )
    hits = [
        *([] if variant.positive is None else variant.positive.recovered_ids),
        *([] if variant.negative is None else variant.negative.admitted_ids),
    ]
    return ScoredVariant(
        label=label,
        search_name=search,
        mcc=metrics.mcc,
        balanced_accuracy=metrics.balanced_accuracy,
        f1=metrics.f1_score,
        sensitivity=metrics.sensitivity,
        precision=metrics.precision,
        control_hits=hits,
    )


def sweep_comparison(result: dict[str, Any]) -> ScoredComparison:
    """The settings a sweep scored, best first, each named by what it varied."""
    table = _SweepTable.model_validate(result)
    varied = _varied(table.variants)
    ranked = sorted(
        table.variants,
        key=lambda v: (v.status != "success", -(v.score or 0.0)),
    )
    labels = {
        v.variant_id: ", ".join(v.params[name].to_wire() for name in varied)
        or v.variant_id
        for v in ranked
    }
    winner = next((v for v in ranked if v.status == "success"), None)
    return ScoredComparison(
        variants=[_scored(v, labels[v.variant_id], table.search_name) for v in ranked],
        winner_label=None if winner is None else labels[winner.variant_id],
        objective=table.objective,
    )


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
    table = DataChunk(
        type="data-scored-comparison",
        data=sweep_comparison(outcome.result).model_dump(by_alias=True, mode="json"),
    )
    return [
        table,
        *summary_chunks(
            tool_call_id,
            f"{len(sweep.variants)} settings tried, "
            f"best {sweep.objective} {sweep.best.score:.3f}",
        ),
    ]


PARAMETER_SWEEP = declare_durable_tool(
    tool_name="optimize_search_parameters",
    estimated_duration_seconds=900,
    chunks_from_result=_sweep_chunks_from_result,
)


_NO_CONTROLS = (
    "A sweep scores each setting against the controls, and this call names none. "
    "Pass the control set the conversation saved as control_set_id "
    "(list_control_sets names it), or the ids the researcher typed as "
    "positive_controls and negative_controls. Nothing was started and no card "
    "was shown."
)
_TWO_SOURCES = (
    "Pass the saved control set as control_set_id or the ids the researcher "
    "typed as positive_controls and negative_controls, not both. Nothing was "
    "started and no card was shown."
)


def _swept_search(
    ctx: RunContext[LeadDeps], wdk_step_id: int
) -> tuple[str, str] | None:
    """The search and record class of the step this conversation pushed as that id."""
    session = ctx.deps.runtime.strategy_session
    graph = session.get_graph(None)
    sync = session.sync_state
    if graph is None or sync is None:
        return None
    step_id = next(
        (held for held, wdk in sync.wdk_step_ids.items() if wdk == wdk_step_id), None
    )
    step = None if step_id is None else graph.steps.get(step_id)
    if step is None or step.search_name is None:
        return None
    record_class = record_class_of(
        step.id, graph.steps, fallback=graph.record_type or "transcript"
    )
    return step.search_name, record_class


async def sweep_can_run(
    ctx: RunContext[LeadDeps],
    *,
    reply: str,
    wdk_step_id: int,
    control_set_id: str | None = None,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
    parameters: list[str] | None = None,
    budget: int = SWEEP_BUDGET,
) -> None:
    """Refuse a sweep call the worker would refuse, before its card is drawn."""
    del reply, budget
    typed = bool(positive_controls or negative_controls)
    if control_set_id is not None and typed:
        raise ModelRetry(_TWO_SOURCES)
    if control_set_id is None and not typed:
        raise ModelRetry(_NO_CONTROLS)
    swept = None if not parameters else _swept_search(ctx, wdk_step_id)
    if parameters is None or swept is None:
        return
    search_name, record_class = swept
    tunable = await tunable_parameters_of_search(
        ctx.deps.runtime.site_id, record_class, search_name
    )
    unknown = [name for name in parameters if name not in tunable]
    if tunable and unknown:
        msg = (
            f"{search_name} cannot vary {', '.join(unknown)}. Name the parameters "
            f"as the search names them: {', '.join(tunable)}. Nothing was started "
            "and no card was shown."
        )
        raise ModelRetry(msg)


@durable_agent_tool(PARAMETER_SWEEP)
async def optimize_search_parameters(
    ctx: RunContext[LeadDeps],
    *,
    reply: CardReply,
    wdk_step_id: int,
    control_set_id: str | None = None,
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

    A search with nothing tunable is refused by name. Call this directly:
    the researcher approves the run on its card, so never offer a sweep on a
    ``propose_changes`` card and never ask in prose. ``reply`` streams above
    the card and names the parameters, the budget and that the sweep takes
    about fifteen minutes.

    Pass the controls once: the control set the conversation saved as
    ``control_set_id``, which the worker reads whole, or the ids the
    researcher typed in this conversation. A call with neither is refused.

    Durable: the trials run on the worker, the turn ends while they run, and
    you are called again with the result (``variants``, ``best``,
    ``objective``, ``downloads``). Report the winning setting and its score.

    Args:
        reply: Your reply, which the researcher reads above the card.
        wdk_step_id: The built step to tune, by its WDK step id. Read it from
            ``get_live_strategy_state``.
        control_set_id: A saved control set, by the id ``list_control_sets``
            names. Its ids are read on the worker, so none is copied here.
        positive_controls: Known-positive gene ids the step should return.
        negative_controls: Known-negative gene ids it should not return.
        parameters: The parameters to vary, by the name the search gives
            them (``signalp_version``, never its label). Leave it out to vary
            every tunable parameter of that step's search. The control-test
            summary names them.
        budget: The most trials to run. Each trial is one WDK call, so a
            larger budget costs proportionally more time.
    """
    del ctx, reply, wdk_step_id, control_set_id, positive_controls
    del negative_controls, parameters, budget
    msg = "optimize_search_parameters runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)
