"""A column name that matches no column of a step answers the step's countable
columns, and a transform is offered only when the step has none."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.tools.standalone.step_tally import StepColumnPage, step_columns
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.orthomcl_step_columns import serve_sequence_columns
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

PROTEIN_STEP = 227288410
BOOLEAN = "boolean_question_SequenceRecordClasses_SequenceRecordClass"


def _singleton_proteins() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("g1", "singleton proteins", "orthomcl")
    graph.record_type = "sequence"
    graph.steps = flatten_tree(StrategyStepNode(id="step_a", search_name=BOOLEAN))
    graph.steps["step_a"].record_class = "sequence"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"step_a": PROTEIN_STEP})
    return session


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_sequence_columns(monkeypatch, PROTEIN_STEP, BOOLEAN)


@pytest.mark.usefixtures("served")
async def test_the_recorded_organism_name_lists_the_taxon_code_column() -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_proteins())

    page = returned(
        await step_columns(ctx, PROTEIN_STEP, name="organism", countable_only=True),
        StepColumnPage,
    )

    assert (page.matched, page.reach, page.transforms) == (0, "step", [])
    assert [(c.name, c.display_name, c.countable) for c in page.columns] == [
        ("abbreviation", "Taxon Code", True)
    ]
    assert ctx.deps.state.turn_markers.column_reaches == []


@pytest.mark.usefixtures("served")
async def test_a_name_that_matches_only_uncountable_columns_offers_no_transform() -> (
    None
):
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_proteins())

    page = returned(
        await step_columns(ctx, PROTEIN_STEP, name="product"), StepColumnPage
    )

    assert [(c.name, c.countable) for c in page.columns] == [("product", False)]
    assert (page.matched, page.reach, page.transforms) == (1, "step", [])


@pytest.mark.usefixtures("served")
async def test_a_name_that_matches_a_countable_column_lists_only_the_match() -> None:
    ctx = lead_run_context(site_id="orthomcl", strategy_session=_singleton_proteins())

    page = returned(
        await step_columns(ctx, PROTEIN_STEP, name="tax", countable_only=True),
        StepColumnPage,
    )

    assert (page.matched, page.total, page.reach) == (1, 1, "step")
    assert [c.name for c in page.columns] == ["abbreviation"]
