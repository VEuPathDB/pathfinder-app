"""Two or more of the Lead's strategy tools in one turn, in the order it runs them.

A build, a delete, a clear and an edit all write the thread's spec, and each
later call plans against what the earlier one left.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    PROTEOME,
    PROTEOME_PARAM,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
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
    Draft,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)

_FRESH_A = "c_phosphatase"
_FRESH_B = "c_ring_stage"


def _plan_spec() -> OperationalSpec:
    """A framed plan no step answers to yet, so its ids are FRAME's own."""
    spec = built_spec()
    spec.criteria = [
        Criterion(
            id=_FRESH_A,
            text="predicted surface proteins",
            search_name="GenesBySignalPeptide",
            role="seed",
        ),
        Criterion(
            id=_FRESH_B,
            text="expressed in merozoites",
            search_name="GenesByRNASeqEvidence",
            resolved_params={STAGE_PERCENTILE: NumberValue(value=80)},
        ),
    ]
    spec.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, leaf(_FRESH_A), leaf(_FRESH_B))
    )
    return spec


def _unbuilt(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """A turn that entered with a framed plan and no strategy at all."""
    return DisagreementThread(monkeypatch, spec=_plan_spec(), session=session_holding())


def _built(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


def _fresh_pair() -> Draft:
    """What a FRAME pass leaves on an empty workspace: two bound criteria."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [
            Criterion(
                id=_FRESH_A,
                text="phosphatase domain",
                search_name="GenesByPfam",
                role="seed",
                resolved_params={"pfam_id": NumberValue(value=2)},
            ),
            Criterion(
                id=_FRESH_B,
                text="ring stage expression",
                search_name="GenesByRNASeqEvidence",
                resolved_params={STAGE_PERCENTILE: NumberValue(value=70)},
            ),
        ]
        found.structure = SpecStructure(
            root=joined(CombineOp.INTERSECT, leaf(_FRESH_A), leaf(_FRESH_B))
        )
        return found

    return _draft


def _only_the_surface_leaf() -> Draft:
    """A structure the strategy cannot reach: it leaves a live criterion out."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.structure = SpecStructure(root=leaf(SURFACE))
        return found

    return _draft


async def test_a_build_then_a_delete_then_an_edit_plans_over_what_is_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deleted step is gone from the spec, and the edit joins the survivor."""
    thread = _unbuilt(monkeypatch)
    await thread.next_turn()
    await thread.build()
    seed, filtered = thread.criteria
    await thread.delete(filtered)
    thread.frames(with_the_proteome(2), declared=kept(seed))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.criteria == [seed, PROTEOME]
    assert [(op.kind, op.step_id) for op in committed_facts(thread.committed)] == [
        ("deleteStep", filtered),
        ("addLeaf", PROTEOME),
        ("addCombine", _root_of(thread)),
    ]
    assert filtered not in thread.graph.steps
    assert spec_facts(thread.spec) == {seed: {}, PROTEOME: {PROTEOME_PARAM: "2"}}
    assert delta.preserved_step_ids == [seed]
    assert delta.added_step_ids == [PROTEOME]


async def test_a_build_then_a_delete_leaves_the_turn_entry_record_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record the turn started from is the framed spec, re-keyed by the build."""
    thread = _unbuilt(monkeypatch)
    await thread.next_turn()
    await thread.build()
    seed, filtered = thread.criteria

    await thread.delete(filtered)

    assert [c.id for c in thread.before_turn.criteria] == [seed, filtered]
    assert thread.criteria == [seed]
    assert thread.ledger_diff().render() == (
        "kept 1, changed 0, added 0, dropped 1, structure rewired"
    )


async def test_a_clear_then_a_frame_then_a_build_then_an_edit_is_one_new_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing of the cleared strategy reaches the new one's ids or values."""
    thread = _built(monkeypatch)
    await thread.next_turn()
    await thread.clear()
    thread.frames(_fresh_pair(), declared=[])
    framed = await thread.frame()
    await thread.build()
    first, second = thread.criteria
    thread.frames(with_the_proteome(2), declared=kept(first, second))

    delta = await thread.edit()

    assert isinstance(framed, FrameResult)
    assert isinstance(delta, EditDelta)
    assert thread.workspaces[0].criteria == []
    assert sorted(thread.graph.steps) == sorted(
        [first, second, PROTEOME, *_combines(thread)]
    )
    assert {SURFACE, STAGE, ROOT}.isdisjoint(thread.graph.steps)
    assert spec_facts(thread.spec) == {
        first: {"pfam_id": "2"},
        second: {STAGE_PERCENTILE: "70"},
        PROTEOME: {PROTEOME_PARAM: "2"},
    }


def _root_of(thread: DisagreementThread) -> str:
    root = thread.graph.primary_root_id()
    assert root is not None
    return root


def _combines(thread: DisagreementThread) -> list[str]:
    return [
        step_id
        for step_id, step in thread.graph.steps.items()
        if step.search_name is None
    ]


async def test_a_refused_edit_shows_the_retry_the_spec_the_dispatch_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The restore target is the dispatch's own record, values and all."""
    thread = _built(monkeypatch)
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, STAGE, ROOT)
    thread.frames(_only_the_surface_leaf(), declared=kept(SURFACE, STAGE))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert thread.committed == []
    assert facts_of(thread.facts(), SURFACE, STAGE, ROOT) == untouched
    assert spec_facts(thread.spec) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "80", STAGE_TIMEPOINT: "40"},
    }


async def test_a_second_pass_after_a_refusal_succeeds_from_the_restored_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry's workspace is the strategy's own spec, not the refused draft."""
    thread = _built(monkeypatch)
    await thread.next_turn()
    thread.frames(_only_the_surface_leaf(), declared=kept(SURFACE, STAGE))
    await thread.edit()
    thread.frames(with_the_proteome(2), declared=kept(SURFACE, STAGE))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert spec_facts(thread.workspaces[1]) == {
        SURFACE: {},
        STAGE: {STAGE_PERCENTILE: "80", STAGE_TIMEPOINT: "40"},
    }
    assert thread.workspaces[1].structure == built_spec().structure
    assert [op.kind for op in committed_facts(thread.committed)] == [
        "addLeaf",
        "addCombine",
    ]
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, STAGE])
