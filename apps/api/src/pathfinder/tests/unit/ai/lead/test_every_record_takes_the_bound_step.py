"""A step that binds a criterion re-keys every spec the turn holds that names it.

The plan, the answer and both baselines address the step by one id, so a
resumed dispatch never plans against a criterion whose step already exists.
"""

from __future__ import annotations

import pytest
from pydantic_ai.tools import DeferredToolResults
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests.unit.ai.lead._analysis_thread import WAITING, bare_thread, export
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    joined,
    kept,
    leaf,
    session_holding,
)
from pathfinder.tests.unit.ai.lead.test_an_analysis_criterion_across_edits import (
    _a_comparison_waits,
)


def _ids(thread: DisagreementThread) -> dict[str, list[str]]:
    domain = thread.deps.state.domain
    held = {
        "plan": domain.operational_spec,
        "answered": domain.answered_spec,
        "before_turn": domain.spec_before_turn,
        "before_dispatch": domain.spec_before_dispatch,
    }
    return {
        name: [] if spec is None else [c.id for c in spec.criteria]
        for name, spec in held.items()
    }


async def _bound(thread: DisagreementThread) -> tuple[str, str]:
    """Frame 24 h over 36 h waiting, edit, then export it by its id."""
    first = await _a_comparison_waits(thread)
    thread.frames(lambda found: found, declared=kept(first))
    assert isinstance(await thread.edit(), EditDelta)
    second = await export(thread, reference="36h", criterion_id=WAITING)
    return first, second.step_id


async def test_no_record_names_the_waiting_id_after_the_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)

    first, second = await _bound(thread)

    assert _ids(thread) == {
        "plan": [first, second],
        "answered": [first, second],
        "before_turn": [first, second],
        "before_dispatch": [first, second],
    }


async def test_the_turn_entry_after_the_export_names_no_waiting_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first, second = await _bound(thread)

    await thread.next_turn()

    assert set(map(tuple, _ids(thread).values())) == {(first, second)}


async def test_a_resumed_edit_whose_record_predates_the_export_keeps_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first, second = await _bound(thread)
    await thread.next_turn(resumes_parked_call=True)
    thread.frames(lambda found: found, declared=kept(first, second))

    delta = await thread.edit(
        resume=SubAgentResume(messages=[], results=DeferredToolResults())
    )

    assert isinstance(delta, EditDelta)
    assert delta.operations_applied == 0
    assert [c.id for c in thread.spec.criteria] == [first, second]


async def test_a_build_re_keys_the_dispatch_record_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = OperationalSpec(
        goal="secreted kinases",
        criteria=[
            Criterion(id="c_kin", text="kinases", search_name="GenesByText"),
            Criterion(id="c_sec", text="secreted", search_name="GenesBySignalPeptide"),
        ],
        structure=SpecStructure(
            root=joined(CombineOp.INTERSECT, leaf("c_kin"), leaf("c_sec"))
        ),
    )
    thread = DisagreementThread(monkeypatch, spec=spec, session=session_holding())
    thread.deps.state.domain.spec_before_dispatch = spec.model_copy(deep=True)
    thread.deps.state.domain.spec_before_turn = spec.model_copy(deep=True)

    await thread.build()

    ids = _ids(thread)
    assert ids["before_dispatch"] == ids["plan"] == ids["before_turn"]
    assert set(ids["plan"]) <= set(thread.graph.steps)
