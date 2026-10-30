"""A step tally names the step it counted and the strategy's result step, and a
reply that cites a tally of another step while no tally counts the result is
refused, with a hint to count the result step."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.tools.standalone import step_tally
from pathfinder.ai.tools.standalone.step_tally import count_step_by_column
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment.column_tally import ColumnTally
from pathfinder.services.experiment.step_tally import CountedStep
from pathfinder.services.experiment.tally_rows import TallyRow
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

_GROUPS = 227288250
_TAXA = 227288270
_ROOT = 227288280


def _session() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("g1", "groups of one protein in a taxon", "orthomcl")
    graph.record_type = "sequence"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="combined",
            search_name="boolean_question_sequence",
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="proteins",
                search_name="FromGroups",
                primary_input=StrategyStepNode(
                    id="groups", search_name="GroupsBySequenceCount"
                ),
            ),
            secondary_input=StrategyStepNode(id="taxa", search_name="ByTaxonomy"),
        )
    )
    graph.steps["groups"].record_class = "group"
    for step in ("proteins", "taxa", "combined"):
        graph.steps[step].record_class = "sequence"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={
            "groups": _GROUPS,
            "proteins": 227288260,
            "taxa": _TAXA,
            "combined": _ROOT,
        },
        wdk_strategy_id=214647290,
        wdk_step_tree=WDKStepTree(step_id=_ROOT),
    )
    return session


async def _tally(step: CountedStep, column: str, top: int) -> ColumnTally:
    del top
    return ColumnTally(
        id=f"tally_{step.wdk_step_id}",
        title="Proteins by Taxon Code",
        search_name=step.search_name,
        record_type=step.record_type,
        record_noun=step.record_noun,
        column=column,
        column_label="Taxon Code",
        total=333932 if step.wdk_step_id == _TAXA else 2744,
        distinct=61,
        rows=[TallyRow(value="pyxn", count=7666 if step.wdk_step_id == _TAXA else 90)],
        site_id=step.site_id,
        wdk_step_id=step.wdk_step_id,
    )


@pytest.fixture(autouse=True)
def _counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(step_tally, "run_step_tally", _tally)


async def test_a_tally_of_a_leaf_names_the_result_step_it_is_not() -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_session())

    result = await count_step_by_column(ctx, _TAXA, "abbreviation")

    (fact,) = ctx.deps.state.turn_markers.tallies
    assert (fact.wdk_step_id, returned(result, ColumnTally).result_step_id) == (
        _TAXA,
        _ROOT,
    )
    assert fact.counts_another_step(_ROOT)
    assert fact.lines(_ROOT)[0] == (
        f"Proteins by Taxon Code, counted on step {_TAXA}, not on the result "
        f"step {_ROOT}"
    )


async def test_a_tally_of_the_root_counts_the_result() -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_session())

    result = await count_step_by_column(ctx, _ROOT, "abbreviation")

    (fact,) = ctx.deps.state.turn_markers.tallies
    assert (fact.wdk_step_id, returned(result, ColumnTally).result_step_id) == (
        _ROOT,
        _ROOT,
    )
    assert not fact.counts_another_step(_ROOT)
    assert fact.lines(_ROOT)[0] == "Proteins by Taxon Code"
