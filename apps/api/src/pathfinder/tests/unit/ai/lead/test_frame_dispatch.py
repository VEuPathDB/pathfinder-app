"""The FRAME dispatch: what it accepts, how it is sized, and when it retries."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import PhaseRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)


def _deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt="find kinases"))


def _four_requirements(deps: LeadDeps) -> None:
    deps.state.domain.requirements = [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        requirement(ConstraintKind.DATA_TYPE, "expression dataset", "trophozoite"),
        requirement(ConstraintKind.PERCENTILE, "high expression", "top 10%"),
        requirement(ConstraintKind.STATISTICAL_THRESHOLD, "dN/dS", "> 1.0"),
    ]


def _stub_stream(
    monkeypatch: pytest.MonkeyPatch,
    result: FrameResult,
    *,
    binds: bool = False,
) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        if binds:
            agent_deps: AgentDeps = kwargs["agent_deps"]
            agent_deps.agent_state.operational_spec_draft.criteria.append(
                Criterion(id="c1", text="kinases", search_name="GenesByText")
            )
        return result

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


async def test_spec_ready_over_an_empty_draft_is_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_stream(monkeypatch, FrameResult(disposition="spec_ready", summary="done"))

    deps = _deps()

    with pytest.raises(ModelRetry) as excinfo:
        await run_frame(
            deps=deps,
            parent_tool_call_id="t1",
            work_order=frame_work_order("frame it", deps.state),
        )

    message = str(excinfo.value)
    assert "set_criterion" in message
    assert "set_structure" in message
    assert "drop_criterion" in message


async def test_the_questions_frame_cannot_answer_are_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass that stops on the user leaves the thread waiting on its answers."""
    _stub_stream(
        monkeypatch,
        FrameResult(
            disposition="needs_user",
            summary="which dataset?",
            open_questions=["Which gametocyte RNA-seq study?", "What counts as a SNP?"],
        ),
    )
    deps = _deps()

    await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps.state),
    )

    assert [q.question for q in deps.state.domain.open_questions] == [
        "Which gametocyte RNA-seq study?",
        "What counts as a SNP?",
    ]


async def test_a_pass_that_asks_nothing_records_no_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = FrameResult(disposition="spec_ready", summary="bound one")
    _stub_stream(monkeypatch, delta, binds=True)
    deps = _deps()

    await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps.state),
    )

    assert deps.state.domain.open_questions == []


async def test_spec_ready_with_one_bound_criterion_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = FrameResult(disposition="spec_ready", summary="bound one")
    _stub_stream(monkeypatch, delta, binds=True)
    deps = _deps()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps.state),
    )

    assert result == delta
    assert deps.state.domain.operational_spec is not None


async def test_second_empty_result_becomes_needs_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_stream(monkeypatch, FrameResult(disposition="spec_ready", summary="done"))
    deps = _deps()

    with pytest.raises(ModelRetry):
        await run_frame(
            deps=deps,
            parent_tool_call_id="t1",
            work_order=frame_work_order("frame it", deps.state),
        )
    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t2",
        work_order=frame_work_order("again", deps.state),
    )

    assert isinstance(result, FrameResult)
    assert result.disposition == "needs_user"
    assert "no bound criterion" in result.summary


async def test_a_needs_user_result_over_an_empty_draft_is_not_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = FrameResult(disposition="needs_user", summary="which dataset?")
    _stub_stream(monkeypatch, delta)

    deps = _deps()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps.state),
    )

    assert result == delta


async def test_an_exhausted_budget_still_reports_the_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)

    deps = _deps()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps.state),
    )

    assert isinstance(result, FrameResult)
    assert result.disposition == "needs_user"
    assert "budget" in result.summary


@pytest.fixture
def declared_sizes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The size every dispatch runs at, in dispatch order."""
    sizes: list[int] = []

    async def _capture(*, run: PhaseRun, **kwargs: object) -> None:
        del kwargs
        sizes.append(run.declared_criteria)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _capture)
    return sizes


async def test_a_declaration_below_the_thread_is_raised_to_it(
    declared_sizes: list[int],
) -> None:
    deps = _deps()
    deps.state.domain.spec_before_turn = OperationalSpec(
        goal="find the kinases",
        criteria=[Criterion(id=f"c{i}", text=f"criterion {i}") for i in range(8)],
    )

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("re-frame after the clarification", deps.state),
        expected_criteria=3,
    )

    assert isinstance(result, FrameResult)
    assert declared_sizes == [8]


async def test_the_requirements_the_thread_states_are_the_floor(
    declared_sizes: list[int],
) -> None:
    deps = _deps()
    _four_requirements(deps)

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("re-frame after the clarification", deps.state),
        expected_criteria=3,
    )

    assert declared_sizes == [4]


async def test_a_declaration_above_the_thread_stands(
    declared_sizes: list[int],
) -> None:
    deps = _deps()
    deps.state.domain.requirements = [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
    ]

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("operationalize the goal", deps.state),
        expected_criteria=9,
    )

    assert declared_sizes == [9]


@pytest.fixture
def stopping_dispatches(monkeypatch: pytest.MonkeyPatch) -> list[PhaseRun]:
    """Every dispatch, each stopping on its budget after binding one criterion."""
    runs: list[PhaseRun] = []

    async def _stub(
        *, run: PhaseRun, agent_deps: AgentDeps, deps: LeadDeps, **kwargs: object
    ) -> None:
        del kwargs
        deps.last_phase_stop = None
        runs.append(run)
        draft = agent_deps.agent_state.operational_spec_draft
        index = len(draft.criteria)
        draft.criteria.append(
            Criterion(
                id=f"c{index}",
                text=f"criterion {index}",
                search_name="GenesByText",
            ),
        )
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=index + 1,
            criteria_declared=run.declared_criteria,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)
    return runs


@pytest.fixture
def barren_dispatches(monkeypatch: pytest.MonkeyPatch) -> list[PhaseRun]:
    """Every dispatch, each stopping on its budget having bound nothing."""
    runs: list[PhaseRun] = []

    async def _stub(*, run: PhaseRun, deps: LeadDeps, **kwargs: object) -> None:
        del kwargs
        runs.append(run)
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=0,
            criteria_declared=run.declared_criteria,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)
    return runs


async def test_a_budget_stop_with_progress_is_dispatched_again(
    stopping_dispatches: list[PhaseRun],
) -> None:
    deps = _deps()
    _four_requirements(deps)

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("operationalize the goal", deps.state),
        expected_criteria=3,
    )

    assert isinstance(result, FrameResult)
    assert [run.declared_criteria for run in stopping_dispatches] == [4, 4]
    assert "c0" in stopping_dispatches[1].work_order


async def test_an_edit_continues_as_an_edit(
    stopping_dispatches: list[PhaseRun],
) -> None:
    deps = _deps()
    deps.state.domain.spec_before_turn = OperationalSpec(
        goal="find the kinases",
        criteria=[
            Criterion(id="k1", text="kinase domain", search_name="GenesByText"),
        ],
    )

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("change the organism", deps.state),
        expected_criteria=3,
    )

    assert len(stopping_dispatches) == 2
    assert stopping_dispatches[1].work_order.startswith("EDIT work order:")


async def test_the_automatic_retry_runs_once_per_turn(
    stopping_dispatches: list[PhaseRun],
) -> None:
    deps = _deps()

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("operationalize the goal", deps.state),
        expected_criteria=3,
    )

    assert len(stopping_dispatches) == 2
    assert deps.frame_retried_after_stop is True


async def test_a_stop_that_bound_nothing_is_not_dispatched_again(
    barren_dispatches: list[PhaseRun],
) -> None:
    deps = _deps()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("operationalize the goal", deps.state),
        expected_criteria=3,
    )

    assert isinstance(result, FrameResult)
    assert len(barren_dispatches) == 1
    assert result.disposition == "needs_user"
    assert "no criteria bound" in result.summary
