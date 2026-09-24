"""The export stores its step's analysis kind, and every write path after it
records the answered tree with that kind."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.tests.unit.ai.lead._analysis_thread import bare_thread, export
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    kept,
)


def _answered_kinds(thread: DisagreementThread) -> dict[str, StampedKind]:
    answered = thread.deps.state.domain.answered_graph
    assert answered is not None
    return StepWords.of(answered).analysis_kinds


async def test_the_export_stores_its_kind_and_the_answer_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)

    first = await export(thread, reference="18h")

    assert thread.graph.analysis_kinds == {
        first.step_id: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }
    assert _answered_kinds(thread) == {
        first.step_id: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }


async def test_an_edit_a_turn_entry_and_a_second_export_keep_every_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first = await export(thread, reference="18h")
    thread.frames(lambda found: found, declared=kept(first.step_id))
    assert isinstance(await thread.edit(), EditDelta)
    await thread.next_turn()

    second = await export(
        thread, reference="36h", combine_with_root=CombineOp.INTERSECT
    )

    expected = {
        first.step_id: StampedKind(
            search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE
        ),
        second.step_id: StampedKind(
            search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE
        ),
    }
    assert (thread.graph.analysis_kinds, _answered_kinds(thread)) == (
        expected,
        expected,
    )


async def test_a_delete_takes_the_kind_off_with_its_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = bare_thread(monkeypatch)
    first = await export(thread, reference="18h")
    second = await export(
        thread, reference="36h", combine_with_root=CombineOp.INTERSECT
    )

    await thread.delete(second.step_id)

    assert _answered_kinds(thread) == {
        first.step_id: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }
