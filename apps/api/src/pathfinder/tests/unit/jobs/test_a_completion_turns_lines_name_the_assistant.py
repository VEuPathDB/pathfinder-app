from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import DurableTaskResult
from assistant_core.platform.context import PhaseOverrides
from assistant_core.tasks.completion_turn import CompletionTurn

from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.jobs import completion
from pathfinder.tests._support.rendered_logs import rendered_logs

_KEYS = ("assistant_id",)


@asynccontextmanager
async def _keys(**kwargs: object) -> AsyncIterator[None]:
    del kwargs
    yield


async def _logging_turn(**kwargs: Any) -> None:
    del kwargs
    logging.getLogger("pydantic_ai").warning("completion line")


async def test_a_completion_turn_names_its_assistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completion, "turn_keys", _keys)
    monkeypatch.setattr(completion, "run_turn", _logging_turn)
    result = DurableTaskResult(task_id=uuid4(), status="success")
    turn = CompletionTurn(
        spec=build_pathfinder_spec(),
        compiled_graph=cast("Any", None),
        memory_store=cast("Any", None),
        writer=cast("Any", None),
        conversation_id=uuid4(),
        user_id=uuid4(),
        phase_overrides=PhaseOverrides(),
        durable_result=result,
        durable_results=(result,),
    )

    with rendered_logs() as logs:
        await completion.open_completion_turn(turn)
        logging.getLogger("pydantic_ai").warning("after the completion")

    line = logs.line("completion line")
    assert line["assistant_id"] == "pathfinder"
    assert set(_KEYS) & set(logs.line("after the completion")) == set()
