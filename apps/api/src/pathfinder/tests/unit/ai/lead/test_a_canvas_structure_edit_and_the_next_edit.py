"""A step added or removed in the graph editor, and the edit that follows it.

The refresh states every live step the spec leaves out and takes out the
criteria the strategy lost, so the next edit plans over what the researcher
actually has.
"""

from __future__ import annotations

import pytest
from pydantic_ai.tools import DeferredToolResults
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
)

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import record_the_spec_the_dispatch_found
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    CANVAS,
    NESTED_ROOT,
    PROTEOME,
    PROTEOME_PARAM,
    THIRD,
    THIRD_PARAM,
    canvas_deletes,
    canvas_step,
    nested_spec,
    nested_tree,
    tree_with_the_canvas_step,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
    OpFacts,
    committed_facts,
    facts_of,
    spec_facts,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    kept,
    recorded,
    session_holding,
    stage_step,
    surface_step,
)

_ORTHOLOGS = "step_7a8b9c0d"
_NESTED_CANVAS = "step_8b9c0d1e"
_PROTEOME_SEARCH = "GenesByMassSpec"
_ADD_LEAF = OpFacts(
    kind="addLeaf",
    step_id=PROTEOME,
    parameters={PROTEOME_PARAM: "2"},
    search_name=_PROTEOME_SEARCH,
    slot="new-root",
)


def _nested_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """A three-search strategy, every criterion on its own step."""
    return DisagreementThread(
        monkeypatch,
        spec=nested_spec(),
        session=session_holding(nested_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT, THIRD, NESTED_ROOT),
    )


def _new_root(thread: DisagreementThread) -> str:
    root = thread.graph.primary_root_id()
    assert root is not None
    return root


def _nested_canvas_tree() -> StrategyStepNode:
    """The canvas joins a new step to the surface leaf, under the live root."""
    return StrategyStepNode(
        id=ROOT,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id=_NESTED_CANVAS,
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=surface_step(),
            secondary_input=canvas_step(),
        ),
        secondary_input=stage_step(),
    )


async def test_a_step_added_in_a_nested_position_is_stated_where_the_canvas_put_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refresh keeps the editor's nesting and its operator, and the edit keeps both."""
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(_nested_canvas_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    assert thread.criteria == [SURFACE, STAGE, CANVAS]
    untouched = facts_of(thread.facts(), SURFACE, STAGE, CANVAS, _NESTED_CANVAS, ROOT)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, CANVAS))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        _ADD_LEAF,
        OpFacts(
            kind="addCombine",
            step_id=_new_root(thread),
            operator="INTERSECT",
            left_id=ROOT,
            right_id=PROTEOME,
        ),
    ]
    assert facts_of(thread.facts(), SURFACE, STAGE, CANVAS, _NESTED_CANVAS, ROOT) == (
        untouched
    )
    assert thread.graph.steps[_NESTED_CANVAS].operator is CombineOp.UNION
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, STAGE, CANVAS])


def _transform_over_the_root() -> StrategyStepNode:
    return StrategyStepNode(
        id=_ORTHOLOGS,
        search_name="GenesByOrthologs",
        display_name="P. vivax orthologs",
        parameters={"organism": MultiPickValue(values=["P. vivax P01"])},
        primary_input=built_tree(),
    )


async def test_a_transform_added_over_the_root_is_stated_and_keeps_its_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The editor's transform becomes a criterion of its own, still over the root."""
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(_transform_over_the_root()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    assert thread.criteria == [SURFACE, STAGE, _ORTHOLOGS]
    assert spec_facts(thread.spec)[_ORTHOLOGS] == {"organism": '["P. vivax P01"]'}
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, _ORTHOLOGS))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        _ADD_LEAF,
        OpFacts(
            kind="addCombine",
            step_id=_new_root(thread),
            operator="INTERSECT",
            left_id=_ORTHOLOGS,
            right_id=PROTEOME,
        ),
    ]
    assert thread.graph.steps[_ORTHOLOGS].primary_input_id == ROOT


async def test_a_leaf_deleted_on_the_canvas_leaves_the_spec_and_the_combine_collapses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nested combine goes with its leaf and the sibling takes its place."""
    thread = _nested_thread(monkeypatch)
    dropped = canvas_deletes(thread.graph, STAGE)

    await thread.next_turn()

    assert dropped == sorted([ROOT, STAGE])
    assert thread.criteria == [SURFACE, THIRD]
    assert thread.graph.steps[NESTED_ROOT].primary_input_id == SURFACE
    assert spec_facts(thread.spec) == {SURFACE: {}, THIRD: {THIRD_PARAM: "Pf3D7"}}


async def test_an_edit_after_a_canvas_delete_plans_over_what_is_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deleted criterion is nobody's to account for, and the survivors keep their ids."""
    thread = _nested_thread(monkeypatch)
    canvas_deletes(thread.graph, STAGE)
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, THIRD, NESTED_ROOT)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, THIRD))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        _ADD_LEAF,
        OpFacts(
            kind="addCombine",
            step_id=_new_root(thread),
            operator="INTERSECT",
            left_id=NESTED_ROOT,
            right_id=PROTEOME,
        ),
    ]
    assert facts_of(thread.facts(), SURFACE, THIRD, NESTED_ROOT) == untouched
    assert STAGE not in thread.graph.steps
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, THIRD])
    assert delta.diff.render() == (
        "kept 2, changed 0, added 1, dropped 0, structure rewired"
    )


async def test_the_roots_secondary_deleted_on_the_canvas_collapses_onto_its_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole taxon branch goes, and the strategy roots on what it joined."""
    thread = _nested_thread(monkeypatch)
    dropped = canvas_deletes(thread.graph, THIRD)

    await thread.next_turn()

    assert dropped == sorted([NESTED_ROOT, THIRD])
    assert thread.criteria == [SURFACE, STAGE]
    assert thread.graph.primary_root_id() == ROOT
    assert spec_facts(thread.spec) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "80", STAGE_TIMEPOINT: "40"},
    }


async def test_a_step_added_while_a_call_was_parked_is_stated_by_the_resumed_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resumed turn is refreshed like any other, so the edit plans over the step."""
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    record_the_spec_the_dispatch_found(thread.deps, resume=None)
    thread.session.graph = session_holding(tree_with_the_canvas_step()).graph
    await thread.next_turn(resumes_parked_call=True)
    assert thread.criteria == [SURFACE, STAGE, CANVAS]
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit(
        resume=SubAgentResume(messages=[], results=DeferredToolResults())
    )

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]
    assert CANVAS in thread.graph.steps
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, STAGE, CANVAS])


async def test_a_step_added_while_a_call_was_parked_is_stated_by_the_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh turn runs the reconciliation the resumed one skips, and the edit lands."""
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(tree_with_the_canvas_step()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE, CANVAS))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.criteria == [SURFACE, STAGE, CANVAS, PROTEOME]
    assert [op.kind for op in committed_facts(thread.committed)] == [
        "addLeaf",
        "addCombine",
    ]
    assert CANVAS in thread.graph.steps
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, STAGE, CANVAS])
