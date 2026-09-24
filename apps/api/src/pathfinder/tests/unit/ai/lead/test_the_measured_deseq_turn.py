"""The measured DESeq2 turn, end to end: one comparison exported, the second
framed as waiting for its analysis, and both built by the analysis workflow."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StepKind
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_pins import eda_route_blocks
from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.domain.strategy.operational_spec import SpecStructure
from pathfinder.tests._support.eda_step_doubles import DE_DATASET
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._analysis_thread import (
    REQUEST,
    WAITING,
    bare_thread,
    bindings,
    export,
    with_the_waiting_comparison,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    joined,
    kept,
    leaf,
)
from pathfinder.tests.unit.ai.lead.conftest import user_intent


def _versus(reference: str) -> EdaComparison:
    return EdaComparison(group_a=[reference], group_b=["24h"])


async def test_an_export_with_no_spec_leaves_an_analysis_criterion_and_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)

    first = await export(thread, reference="18h")

    [criterion] = thread.spec.criteria
    assert criterion.id == first.step_id
    assert criterion.analysis is not None
    assert criterion.analysis.words == (
        "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)"
    )
    assert criterion.resolved_params == {}
    assert thread.spec.goal == REQUEST
    assert thread.answered == thread.spec


async def test_the_second_comparison_waits_and_the_edit_commits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first = await export(thread, reference="18h")
    thread.frames(
        with_the_waiting_comparison(first.step_id), declared=kept(first.step_id)
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert (delta.operations_applied, thread.committed[1:]) == (0, [])
    assert [c.id for c in thread.spec.criteria] == [first.step_id, WAITING]
    assert [c.id for c in thread.answered.criteria] == [first.step_id]
    order = thread.work_orders[-1]
    assert (
        f"- [{first.step_id}] Genes higher in 24h than in 18h (DESeq, |effect| >= 1, "
        f"p <= 0.05) -> analysis workflow, BOUND: keep it"
    ) in order
    assert "eda_analysis_spec" not in order


async def test_the_route_names_the_waiting_comparison_by_its_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first = await export(thread, reference="18h")
    thread.frames(
        with_the_waiting_comparison(first.step_id), declared=kept(first.step_id)
    )
    await thread.edit()
    thread.deps.intent = user_intent(IntentClassification.EDIT_STRATEGY)
    thread.deps.state.turn_markers.intent_classified = True

    [block] = eda_route_blocks(run_context_for(thread.deps))

    assert block.splitlines()[2:6] == [
        f'1. open_eda_analysis(dataset_id="{DE_DATASET}", purpose=...)',
        "2. set_eda_filters - once for the sheet, once with the filters array",
        "3. preview_eda_subset, and run_eda_compute when it compares groups",
        (
            f'4. create_eda_step(criterion_id="{WAITING}") - the structure places '
            f"the step, so name no other placement."
        ),
    ]


async def test_both_comparisons_are_deseq2_branches_with_a_significance_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first = await export(thread, reference="18h")
    thread.frames(
        with_the_waiting_comparison(first.step_id), declared=kept(first.step_id)
    )
    await thread.edit()

    second = await export(thread, reference="36h", criterion_id=WAITING)

    assert second.combined_with_root is CombineOp.INTERSECT
    root = thread.graph.steps[thread.graph.primary_root_id() or ""]
    assert (root.kind, root.operator) == (StepKind.COMBINE, CombineOp.INTERSECT)
    assert (root.primary_input_id, root.secondary_input_id) == (
        first.step_id,
        second.step_id,
    )
    searches = sorted(
        step.search_name for step in thread.graph.steps.values() if step.search_name
    )
    assert searches == [COMPUTE_QUERY, COMPUTE_QUERY]
    assert {
        step_id: (b.method, b.effect_direction, b.significance_threshold, b.comparison)
        for step_id, b in bindings(thread).items()
    } == {
        first.step_id: ("DESeq", "upOnly", 0.05, _versus("18h")),
        second.step_id: ("DESeq", "upOnly", 0.05, _versus("36h")),
    }
    assert [c.id for c in thread.spec.criteria] == [first.step_id, second.step_id]
    assert thread.spec.structure == SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(first.step_id), leaf(second.step_id))
    )
    assert thread.answered == thread.spec
