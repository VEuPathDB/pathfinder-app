from __future__ import annotations

from pydantic import TypeAdapter
from pydantic_ai import ToolFailed
from veupathdb.domain.strategy import subtree_ids

from strategist.ai.capabilities.site_reads import read_in_time
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone.results import READ_DEADLINE_SECONDS
from strategist.domain.comparison_facts import ComparisonFact
from strategist.domain.strategy.ranking import score_rows
from strategist.domain.strategy.record_class_check import step_class_of
from strategist.services.experiment.paged_tally import count_paged_values

_WEIGHT_COLUMN = "wdk_weight"
_SCORES: TypeAdapter[dict[int, int]] = TypeAdapter(dict[int, int])


async def record_score_counts(deps: LeadDeps) -> None:
    session = deps.runtime.strategy_session
    graph, sync = session.get_graph(None), session.sync_state
    root_id = None if graph is None else graph.primary_root_id()
    if graph is None or sync is None or root_id not in sync.wdk_step_ids:
        return
    weights = [
        weight
        for step_id in subtree_ids(root_id, graph.steps)
        if (weight := graph.steps[step_id].wdk_weight) is not None
    ]
    if not weights:
        return
    wdk_step_id = sync.wdk_step_ids[root_id]
    try:
        paged = await read_in_time(
            "the score count",
            f"step {wdk_step_id}",
            count_paged_values(
                session.site_id,
                wdk_step_id,
                step_class_of(graph.steps, root_id),
                _WEIGHT_COLUMN,
            ),
            deadline=READ_DEADLINE_SECONDS,
        )
    except ToolFailed:
        return
    if paged.counts.total() < paged.total:
        return
    scores = _SCORES.validate_python(dict(paged.counts))
    fact = ComparisonFact(
        variants=score_rows(scores, top=sum(weights)), on_its_card=False
    )
    markers = deps.state.turn_markers
    if fact not in markers.comparisons:
        markers.record_comparison(fact)


__all__ = ["record_score_counts"]
