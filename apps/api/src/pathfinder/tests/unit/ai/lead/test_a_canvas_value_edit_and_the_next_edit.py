"""What the graph editor writes between turns, and what the next edit does to it.

Each test commits the canvas edit the way the graph route commits one, runs the
production pre-turn refresh and one edit dispatch, and states the whole account:
the operations, the steps the request never named, the committed spec, the
delta and the ledger.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    PROTEOME_PARAM,
    canvas_flips,
    canvas_renames,
    canvas_sets,
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
)

_PROTEOME_SEARCH = "GenesByMassSpec"


def _thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _added_proteome(new_root: str, *, joined_to: str) -> list[OpFacts]:
    """The two operations that hang the proteome criterion off the strategy."""
    return [
        OpFacts(
            kind="addLeaf",
            step_id=PROTEOME,
            parameters={PROTEOME_PARAM: "2"},
            search_name=_PROTEOME_SEARCH,
            slot="new-root",
        ),
        OpFacts(
            kind="addCombine",
            step_id=new_root,
            operator="INTERSECT",
            left_id=joined_to,
            right_id=PROTEOME,
        ),
    ]


def _new_root(thread: DisagreementThread) -> str:
    root = thread.graph.primary_root_id()
    assert root is not None
    return root


async def test_a_value_set_on_the_canvas_reaches_the_spec_and_is_not_written_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole account of the edit: two adds, and the canvas value stands."""
    thread = _thread(monkeypatch)
    canvas_sets(thread.graph, STAGE, timepoint=NumberValue(value=48))
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, STAGE, ROOT)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == _added_proteome(
        _new_root(thread), joined_to=ROOT
    )
    assert facts_of(thread.facts(), SURFACE, STAGE, ROOT) == untouched
    assert spec_facts(thread.spec) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "80", STAGE_TIMEPOINT: "48"},
        PROTEOME: {PROTEOME_PARAM: "2"},
    }
    assert delta.preserved_step_ids == [SURFACE, STAGE]
    assert delta.added_step_ids == [PROTEOME]
    assert (
        delta.diff.render()
        == "kept 2, changed 0, added 1, dropped 0, structure rewired"
    )
    assert thread.ledger_diff().render() == delta.diff.render()


async def test_a_combine_flipped_on_the_canvas_stands_through_the_next_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph owns the shape, so the spec takes the flip and no edit undoes it."""
    thread = _thread(monkeypatch)
    canvas_flips(thread.graph, ROOT, CombineOp.UNION)
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == _added_proteome(
        _new_root(thread), joined_to=ROOT
    )
    assert thread.graph.steps[ROOT].operator is CombineOp.UNION
    assert [c.criterion_id for c in delta.diff.changes if c.disposition != "kept"] == [
        PROTEOME
    ]
    assert (
        delta.diff.render()
        == "kept 2, changed 0, added 1, dropped 0, structure rewired"
    )


async def test_a_combine_flipped_on_the_canvas_stands_when_the_edit_restates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structure that states the live operator asks for no operator change."""
    thread = _thread(monkeypatch)
    canvas_flips(thread.graph, ROOT, CombineOp.UNION)
    await thread.next_turn()
    restated = thread.spec.model_copy(deep=True)
    assert restated.structure is not None
    restated.structure.root.operator = CombineOp.UNION
    thread.deps.state.domain.operational_spec = restated
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == _added_proteome(
        _new_root(thread), joined_to=ROOT
    )
    assert thread.graph.steps[ROOT].operator is CombineOp.UNION


async def test_a_step_renamed_on_the_canvas_keeps_its_name_through_an_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A display name is the researcher's, and no operation of this edit writes it."""
    thread = _thread(monkeypatch)
    canvas_renames(thread.graph, STAGE, "merozoite, my cutoff")
    await thread.next_turn()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.step_id for op in committed_facts(thread.committed)] == [
        PROTEOME,
        _new_root(thread),
    ]
    assert thread.graph.steps[STAGE].display_name == "merozoite, my cutoff"
    assert delta.preserved_step_ids == [SURFACE, STAGE]


async def test_two_canvas_edits_in_a_row_both_reach_the_next_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value and an operator, set in two commits, both stand at dispatch start."""
    thread = _thread(monkeypatch)
    canvas_sets(thread.graph, STAGE, timepoint=NumberValue(value=48))
    canvas_sets(thread.graph, SURFACE, min_signal=NumberValue(value=3))
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, STAGE)
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == _added_proteome(
        _new_root(thread), joined_to=ROOT
    )
    assert facts_of(thread.facts(), SURFACE, STAGE) == untouched
    assert untouched[STAGE].parameters == {
        STAGE_PERCENTILE: "80",
        STAGE_TIMEPOINT: "48",
    }
    assert untouched[SURFACE].parameters == {"min_signal": "3"}
    assert delta.diff.changed_count == 0
