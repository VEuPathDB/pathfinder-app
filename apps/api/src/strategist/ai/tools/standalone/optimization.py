"""The parameter sweep: a durable, approval-gated search of a built step's settings."""

from __future__ import annotations

from typing import Annotated, Any, Final
from uuid import UUID

from assistant_core.graph.tool_summary import summary_chunks
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.tasks.declaration import declare_durable_tool
from assistant_core.tasks.decorator import DurableOutcome
from pydantic import ConfigDict, Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.controls import ControlTargetData, ControlTestResult

from strategist.ai.graph.turn_records import ControlTestRun
from strategist.ai.lead.card_reply import CardReply
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone._step_read import graph_step_id, read_as
from strategist.ai.tools.standalone.saved_control_sets import (
    unattached_set,
)
from strategist.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    NamedControlSet,
)
from strategist.domain.unread import Unread
from strategist.platform.durable_worker import durable_agent_tool
from strategist.services.evidence.optimization import tunable_parameters_of_search
from strategist.services.experiment.metrics import metrics_from_control_result
from strategist.services.experiment.scored_comparison import (
    ScoredComparison,
    ScoredVariant,
)
from strategist.services.parameter_optimization.config import (
    SWEEP_BUDGET,
    SWEEP_BUDGET_MAX,
    SWEEP_BUDGET_MIN,
    SweepResult,
    SweepVariantResult,
)


class _SweepTrials(CamelModel):
    """The trials a finished sweep reports, each with the controls it filed."""

    model_config = ConfigDict(extra="ignore")

    variants: list[SweepVariantResult] = Field(default_factory=list)
    control_set: NamedControlSet


def sweep_control_runs(
    result: dict[str, Any], *, tool_call_id: str
) -> list[ControlTestRun]:
    """One control result per setting the sweep scored."""
    runs: list[ControlTestRun] = []
    trials = _SweepTrials.model_validate(result)
    for trial in trials.variants:
        positive, negative = trial.positive, trial.negative
        if positive is None and negative is None:
            continue
        runs.append(
            ControlTestRun(
                tool_call_id=f"{tool_call_id}:{trial.variant_id}",
                origin="sweep",
                evidence=ControlTestEvidence(
                    tested_label=f"setting {trial.variant_id}",
                    control_set=trials.control_set,
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


def _varied(variants: list[SweepVariantResult]) -> list[str]:
    """The parameters whose value differs between the settings."""
    names = sorted({name for variant in variants for name in variant.params})
    return [
        name
        for name in names
        if _differ([v.params[name] for v in variants if name in v.params])
    ]


def _differ(values: list[ParamValue]) -> bool:
    return any(value != values[0] for value in values[1:])


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


def sweep_comparison(sweep: SweepResult) -> ScoredComparison:
    """The settings a sweep scored, best first, each named by what it varied."""
    varied = _varied(sweep.variants)
    ranked = sorted(
        sweep.variants,
        key=lambda v: (v.status != "success", -(v.score or 0.0)),
    )
    labels = {
        v.variant_id: ", ".join(v.params[name].to_wire() for name in varied)
        or v.variant_id
        for v in ranked
    }
    winner = next((v for v in ranked if v.status == "success"), None)
    return ScoredComparison(
        variants=[_scored(v, labels[v.variant_id], sweep.search_name) for v in ranked],
        winner_label=None if winner is None else labels[winner.variant_id],
        objective=sweep.ranked_by,
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
    sweep = SweepResult.model_validate(outcome.result)
    table = DataChunk(
        type="data-scored-comparison",
        data=sweep_comparison(sweep).model_dump(by_alias=True, mode="json"),
    )
    return [table, *summary_chunks(tool_call_id, sweep_summary(sweep))]


def sweep_summary(sweep: SweepResult) -> str:
    tried = f"{len(sweep.variants)} settings tried"
    best = sweep.best
    if best is None or best.score is None:
        return f"{tried}, none scored"
    said = f"{tried}, best {sweep.ranked_by} {best.score:.3f}"
    if sweep.false_positives_measured:
        return said
    return f"{said}; no negative controls: false positives not measured"


NO_SET_ATTACHED: Final = (
    "A control set is saved or attached in Build: Build saves the researcher's "
    "ids as a control set, or attaches a saved set the researcher names."
)

PARAMETER_SWEEP = declare_durable_tool(
    tool_name="optimize_search_parameters",
    estimated_duration_seconds=900,
    chunks_from_result=_sweep_chunks_from_result,
)


async def sweep_can_run(
    ctx: RunContext[LeadDeps],
    *,
    reply: str,
    wdk_step_id: int,
    control_set_id: str,
    parameters: list[str] | None = None,
    budget: int = SWEEP_BUDGET,
) -> None:
    """Refuse a sweep call the worker would refuse, before its card is drawn."""
    del reply, budget
    held = ctx.deps.runtime.strategy_session.wdk_step_ids()
    if held and wdk_step_id not in held:
        msg = (
            f"Step {wdk_step_id} is no step of this strategy on the site. Its steps "
            f"are {', '.join(str(i) for i in held)}. Nothing was started and no card "
            "was shown."
        )
        raise ModelRetry(msg)
    refused = unattached_set(control_set_id, ctx.deps.state.domain.control_sets)
    if refused is not None:
        msg = f"{refused} {NO_SET_ATTACHED} Nothing was started and no card was shown."
        raise ModelRetry(msg)
    session = ctx.deps.runtime.strategy_session
    if not parameters or graph_step_id(session, wdk_step_id) is None:
        return
    record_class, search_name = await read_as(session, wdk_step_id)
    if search_name is None:
        return
    match await tunable_parameters_of_search(
        ctx.deps.runtime.site_id, record_class, search_name
    ):
        case Unread(reason=reason):
            msg = (
                f"The parameters {search_name} can vary were not read ({reason}). "
                "Nothing was started and no card was shown."
            )
            raise ModelRetry(msg)
        case read:
            tunable = read
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
    control_set_id: str,
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
    the researcher approves the run on its card, so never offer a sweep on any
    other card and never ask in prose. ``reply`` streams above
    the card and names the parameters, the budget and that the sweep takes
    about fifteen minutes.

    The controls are the control set attached to this conversation, named
    by ``control_set_id`` and read whole on the worker. Ids the researcher
    types are first saved as a control set in Build, which attaches the set.

    Durable: the trials run on the worker, the turn ends while they run, and
    you are called again with the result (``variants``, ``best``,
    ``objective``, ``downloads``). Report the winning setting and its score.

    Args:
        reply: Your reply, which the researcher reads above the card.
        wdk_step_id: The built step to tune, by its WDK step id. Read it from
            ``get_live_strategy_state``.
        control_set_id: A control set attached to this conversation, by its
            id. Its ids are read on the worker, so none is copied here.
        parameters: The parameters to vary, by the name the search gives
            them (``signalp_version``, never its label). Leave it out to vary
            every tunable parameter of that step's search. The control-test
            summary names them.
        budget: The most trials to run. Each trial is one WDK call, so a
            larger budget costs proportionally more time.
    """
    del ctx, reply, wdk_step_id, control_set_id, parameters, budget
    msg = "optimize_search_parameters runs on the worker via @durable_agent_tool"
    raise NotImplementedError(msg)
