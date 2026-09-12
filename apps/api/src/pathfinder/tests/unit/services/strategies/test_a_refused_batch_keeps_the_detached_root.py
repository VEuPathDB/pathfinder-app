"""A refused batch leaves every root of the graph exactly where it was."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_edit_guard import StatedCriterion
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync_state import WDKSyncState

_MIC2 = "step_780fd940"
_DETACHED = "step_b5c6d7e8"
_TEXT = "Cell-cycle expression profile similar to MIC2 (TGME49_201780)"


def _context() -> StrategyMutationContext:
    session = StrategySession(site_id="toxodb")
    graph = StrategyGraph(graph_id="g1", name="Invasion", site_id="toxodb")
    graph.record_type = "transcript"
    graph.steps = {
        **flatten_tree(
            StrategyStepNode(
                id=_MIC2,
                search_name="GenesByToxoProfileSimilarity",
                parameters={"ProfileGeneId": StringValue(value="TGME49_201780")},
            )
        ),
        **flatten_tree(StrategyStepNode(id=_DETACHED, search_name="GenesByText")),
    }
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={_MIC2: 440_432_473, _DETACHED: 440_432_474},
        wdk_strategy_id=330_642_473,
    )
    return StrategyMutationContext(
        site_id="toxodb",
        strategy_session=session,
        stated_values={
            _MIC2: StatedCriterion(
                text=_TEXT,
                values={"ProfileGeneId": StringValue(value="TGME49_201780")},
            )
        },
    )


async def test_a_refused_value_edit_keeps_both_roots() -> None:
    deps = _context()
    graph = deps.strategy_session.graph
    assert graph is not None
    assert sorted(graph.roots) == [_MIC2, _DETACHED]

    with pytest.raises(ApplyError) as excinfo:
        await apply_and_commit(
            deps=deps,
            op=UpdateStepParamsOp(
                step_id=_MIC2,
                parameters={"ProfileGeneId": StringValue(value="TGME49_300100")},
            ),
        )

    assert "set_criterion" in str(excinfo.value)
    assert sorted(graph.roots) == [_MIC2, _DETACHED]
    assert sorted(graph.steps) == [_MIC2, _DETACHED]
    assert graph.steps[_MIC2].parameters == {
        "ProfileGeneId": StringValue(value="TGME49_201780")
    }
