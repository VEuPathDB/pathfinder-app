"""An exported analysis is a criterion the edits after it keep, until the
researcher deletes it."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_pins import eda_route_blocks
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests._support.eda_step_doubles import DE_DATASET
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._analysis_thread import (
    WAITING,
    bare_thread,
    bindings,
    export,
    with_the_waiting_comparison,
)
from pathfinder.tests.unit.ai.lead._disagreement_drafts import with_the_percentile
from pathfinder.tests.unit.ai.lead._disagreement_facts import OpFacts, committed_facts
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    SURFACE,
    DisagreementThread,
    built_spec,
    built_tree,
    declared,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.lead.conftest import user_intent


def _built_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    return DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )


async def test_an_edit_of_another_step_writes_that_step_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _built_thread(monkeypatch)
    exported = await export(
        thread, reference="18h", combine_with_root=CombineOp.INTERSECT
    )
    before = thread.spec.model_copy(deep=True)
    written = len(thread.committed)
    thread.frames(
        with_the_percentile(90),
        declared=[*kept(SURFACE, exported.step_id), *declared("changed", STAGE)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed[written:]) == [
        OpFacts(
            kind="updateStepParams", step_id=STAGE, parameters={STAGE_PERCENTILE: "90"}
        )
    ]
    assert [c.criterion_id for c in delta.diff.changes if c.disposition == "kept"] == [
        SURFACE,
        exported.step_id,
    ]
    held = next(c for c in thread.spec.criteria if c.id == exported.step_id)
    assert held == next(c for c in before.criteria if c.id == exported.step_id)
    assert exported.step_id in bindings(thread)


async def test_only_the_researchers_delete_takes_the_analysis_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _built_thread(monkeypatch)
    exported = await export(
        thread, reference="18h", combine_with_root=CombineOp.INTERSECT
    )

    await thread.delete(exported.step_id)

    assert exported.step_id not in thread.graph.steps
    assert [c.id for c in thread.spec.criteria] == [SURFACE, STAGE]
    assert bindings(thread) == {}


def _two_waiting(kept_id: str) -> OperationalSpec:
    """FRAME states two comparisons on the dataset the export already runs on."""
    return OperationalSpec(
        goal="24 h over 18 h, 36 h and 12 h",
        criteria=[
            Criterion(id=kept_id, text="24 h over 18 h"),
            Criterion(id="c_36", text="24 h over 36 h", needs_analysis_on=DE_DATASET),
            Criterion(id="c_12", text="24 h over 12 h", needs_analysis_on=DE_DATASET),
        ],
        structure=SpecStructure(
            root=joined(CombineOp.INTERSECT, leaf(kept_id), leaf("c_36"), leaf("c_12"))
        ),
    )


async def test_two_comparisons_on_one_dataset_each_wait_and_each_are_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comparison on a dataset is swallowed by another on the same one."""
    thread = bare_thread(monkeypatch)
    first = await export(thread, reference="18h")

    def _draft(found: OperationalSpec) -> OperationalSpec:
        drafted = _two_waiting(first.step_id)
        drafted.criteria[0] = found.criteria[0]
        return drafted

    thread.frames(_draft, declared=kept(first.step_id))
    delta = await thread.edit()
    thread.deps.intent = user_intent(IntentClassification.EDIT_STRATEGY)
    thread.deps.state.turn_markers.intent_classified = True
    routes = eda_route_blocks(run_context_for(thread.deps))

    assert isinstance(delta, EditDelta)
    assert delta.operations_applied == 0
    assert [route.count('criterion_id="c_') for route in routes] == [1, 1]
    assert 'create_eda_step(criterion_id="c_36")' in routes[0]
    assert 'create_eda_step(criterion_id="c_12")' in routes[1]

    thirty_six = await export(thread, reference="36h", criterion_id="c_36")
    twelve = await export(thread, reference="12h", criterion_id="c_12")

    assert sorted(bindings(thread)) == sorted(
        [first.step_id, thirty_six.step_id, twelve.step_id]
    )
    assert [c.id for c in thread.spec.criteria] == [
        first.step_id,
        thirty_six.step_id,
        twelve.step_id,
    ]
    assert thread.answered == thread.spec


async def _a_comparison_waits(thread: DisagreementThread) -> str:
    """Export 24 h over 18 h, then frame 24 h over 36 h waiting beside it."""
    first = await export(thread, reference="18h")
    thread.frames(
        with_the_waiting_comparison(first.step_id), declared=kept(first.step_id)
    )
    assert isinstance(await thread.edit(), EditDelta)
    await thread.next_turn()
    return first.step_id


async def test_a_later_edit_owes_no_disposition_for_a_waiting_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No push carries a waiting criterion, so it is no unpushed change."""
    thread = bare_thread(monkeypatch)
    exported = await _a_comparison_waits(thread)
    thread.frames(lambda found: found, declared=kept(exported))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert delta.operations_applied == 0
    assert "NOT PUSHED YET" not in thread.work_orders[-1]


async def test_binding_a_waiting_criterion_is_a_change_of_that_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ledger reads the bound criterion under its step id, never as a drop."""
    thread = bare_thread(monkeypatch)
    exported = await _a_comparison_waits(thread)

    second = await export(thread, reference="36h", criterion_id=WAITING)

    diff = thread.ledger_diff()
    assert [(c.criterion_id, c.disposition) for c in diff.changes] == [
        (exported, "kept"),
        (second.step_id, "changed"),
    ]
    assert diff.structure_changed is False
