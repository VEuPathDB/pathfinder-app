"""A worker run ends at the turn that answers, not at the turn that parked on a
durable task: the log after the parked turn's ``done`` still owes a reply."""

from __future__ import annotations

from uuid import UUID

from assistant_core.graph.stream_events import (
    background_task_started_event,
    task_completed_event,
    task_progress_event,
)
from assistant_core.platform.types import JSONObject
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DoneChunk,
    FinishChunk,
    StartChunk,
    TextDeltaChunk,
)

from pathfinder.devtools.models import Chunk
from pathfinder.devtools.turn_arc import TurnArc, read_arc

_TASK = UUID("0f0e0d0c-0000-4000-8000-00000000e0a1")
_SECOND = UUID("0f0e0d0c-0000-4000-8000-00000000e0a2")
_EDA = "run_eda_compute"
_CONTROLS = "run_control_tests_on_step"


def _wire(chunk: BaseChunk) -> JSONObject:
    return chunk.model_dump(by_alias=True, exclude_none=True, mode="json")


def _started(task_id: UUID, tool: str) -> JSONObject:
    return _wire(
        background_task_started_event(
            task_id=task_id, tool_name=tool, estimated_duration_seconds=60
        )
    )


def _parked(*tasks: tuple[UUID, str]) -> list[JSONObject]:
    return [
        _wire(StartChunk(message_id="m1")),
        *(_started(task_id, tool) for task_id, tool in tasks),
        _wire(FinishChunk(finish_reason="other")),
        _wire(DoneChunk()),
    ]


def _gap(task_id: UUID) -> list[JSONObject]:
    return [
        _wire(task_progress_event(task_id=task_id, percent=0.5, message="half")),
        _wire(task_completed_event(task_id=task_id, status="success")),
    ]


def _answer(text: str) -> list[JSONObject]:
    return [
        _wire(StartChunk(message_id="m1")),
        _wire(TextDeltaChunk(id="t1", delta=text)),
        _wire(FinishChunk(finish_reason="stop")),
        _wire(DoneChunk()),
    ]


def _arc(chunks: list[JSONObject]) -> TurnArc:
    return read_arc([Chunk.model_validate(chunk) for chunk in chunks])


def test_a_turn_that_parked_on_a_task_is_parked_on_it() -> None:
    assert _arc(_parked((_TASK, _EDA))) == TurnArc(state="parked", parked_on=(_EDA,))


def test_a_task_that_reported_leaves_the_turn_parked() -> None:
    arc = _arc([*_parked((_TASK, _EDA)), *_gap(_TASK)])

    assert arc == TurnArc(state="parked", parked_on=(_EDA,))


def test_the_first_of_two_tasks_to_report_is_not_the_end() -> None:
    arc = _arc([*_parked((_TASK, _CONTROLS), (_SECOND, _CONTROLS)), *_gap(_TASK)])

    assert arc == TurnArc(state="parked", parked_on=(_CONTROLS, _CONTROLS))


def test_the_completion_turn_runs_until_its_done() -> None:
    answer = _answer("Controls ran on 440230693:success.")
    arc = _arc([*_parked((_TASK, _EDA)), *_gap(_TASK), *answer[:2]])

    assert arc.state == "running"


def test_the_completion_turn_s_done_ends_the_run() -> None:
    answer = _answer("Controls ran on 440230693:success.")

    assert _arc([*_parked((_TASK, _EDA)), *_gap(_TASK), *answer]).state == "ended"


def test_a_completion_turn_that_parks_again_is_parked_on_its_own_task() -> None:
    chunks = [*_parked((_TASK, _EDA)), *_gap(_TASK), *_parked((_SECOND, _CONTROLS))]

    assert _arc(chunks) == TurnArc(state="parked", parked_on=(_CONTROLS,))


def test_a_stopped_turn_ends_whatever_it_started() -> None:
    stopped = _parked((_TASK, _EDA))
    stopped.insert(2, {"type": "data-turn-stopped", "data": {}})

    assert _arc(stopped).state == "ended"


def test_a_turn_that_started_no_task_ends_at_its_done() -> None:
    assert _arc(_answer("Here are 209 genes.")).state == "ended"


def test_a_log_with_no_done_is_still_running() -> None:
    assert _arc([]).state == "running"
    assert _arc(_answer("Here are 209 genes.")[:2]).state == "running"
