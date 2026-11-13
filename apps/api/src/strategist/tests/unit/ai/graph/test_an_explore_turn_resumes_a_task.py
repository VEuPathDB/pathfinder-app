from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import DurableTaskResult

from strategist.ai.models.mock.explore_arc import NO_READING
from strategist.ai.tools.standalone.eda_statistics import EDA_PCA
from strategist.ai.tools.standalone.optimization import PARAMETER_SWEEP
from strategist.tests._support.durable_answers import PCA_RESULT, SWEEP_RESULT
from strategist.tests._support.explore_turns import (
    NO_READING_PROMPT,
    ExploreDoubles,
    domain_of,
    explore_state,
    install_explore_doubles,
    parked_durable,
    run_explore,
    update_of,
)


@pytest.fixture
def doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    return install_explore_doubles(monkeypatch)


async def test_a_finished_reduction_resumes_explore_and_keeps_its_statistic(
    doubles: ExploreDoubles,
) -> None:
    del doubles
    task = uuid4()
    parked = parked_durable(
        NO_READING_PROMPT, tool_name=EDA_PCA.tool_name, task=task, args={}
    )
    state = explore_state(
        NO_READING_PROMPT,
        pending_durable_call=parked,
        durable_result=DurableTaskResult(
            task_id=task, status="success", result=PCA_RESULT
        ),
    )

    command = await run_explore(state)

    domain = domain_of(command)
    assert update_of(command)["pending_durable_call"] is None
    assert [statistic.id for statistic in domain.statistics] == ["stat_pca"]
    assert domain.exchanges[-1].kind == "task_result"
    assert domain.exchanges[-1].reply == NO_READING
    assert domain.request_messages == []


async def test_a_finished_task_marks_its_reply_explore(
    doubles: ExploreDoubles,
) -> None:
    task = uuid4()
    parked = parked_durable(
        NO_READING_PROMPT, tool_name=EDA_PCA.tool_name, task=task, args={}
    )
    state = explore_state(
        NO_READING_PROMPT,
        pending_durable_call=parked,
        durable_result=DurableTaskResult(
            task_id=task, status="success", result=PCA_RESULT
        ),
    )

    await run_explore(state)

    assert [c["data"]["route"] for c in doubles.of_type("data-turn-route")] == [
        "explore"
    ]


async def test_a_finished_sweep_files_its_control_runs(
    doubles: ExploreDoubles,
) -> None:
    del doubles
    task = uuid4()
    parked = parked_durable(
        NO_READING_PROMPT,
        tool_name=PARAMETER_SWEEP.tool_name,
        task=task,
        args={"reply": "I will try the settings."},
    )
    state = explore_state(
        NO_READING_PROMPT,
        pending_durable_call=parked,
        durable_result=DurableTaskResult(
            task_id=task, status="success", result=SWEEP_RESULT
        ),
    )

    command = await run_explore(state)

    [run] = domain_of(command).markers_for(state.user_message_id).control_tests
    assert run.tool_call_id == f"{parked.tool_call_id}:v1"
    assert run.origin == "sweep"
    assert run.evidence.positive is not None
    assert run.evidence.positive.returned == ["PF3D7_0100100"]
    assert run.evidence.positive.not_returned == ["PF3D7_0100200"]
    assert update_of(command)["pending_durable_call"] is None
