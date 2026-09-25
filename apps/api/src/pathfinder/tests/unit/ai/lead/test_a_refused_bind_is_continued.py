"""A pass that one tool refused past its retries after binding part of the plan
is continued by the dispatch, once, the way a budget stop is."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch, sub_agent_stream
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_stream import PhaseRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    called_tool_names,
    final_result_part,
    lead_deps,
    pipeline_state,
    tool_script_model,
)

pytestmark = pytest.mark.usefixtures("collector")

_PROMPT = (
    "Find Plasmodium falciparum 3D7 genes with a predicted signal peptide and 2 to "
    "99 transmembrane domains."
)
_REFUSAL = (
    "c_tm: the reason does not hold the term Minimum Number of Transmembrane "
    "Domains. Nothing was recorded."
)
# The toolset's retries, and the refusals that pass them.
_RETRIES = 3
_REFUSED_ATTEMPTS = _RETRIES + 1


class _Site:
    """How many times the transmembrane bind was attempted."""

    attempts = 0


async def bind_signal_peptide(ctx: RunContext[AgentDeps]) -> str:
    """Bind the signal-peptide criterion once, however often it is called."""
    draft = ctx.deps.agent_state.operational_spec_draft
    if not any(c.id == "c_sp" for c in draft.criteria):
        draft.criteria.append(
            Criterion(
                id="c_sp", text="signal peptide", search_name="GenesWithSignalPeptide"
            )
        )
    return "bound"


async def bind_transmembrane(ctx: RunContext[AgentDeps]) -> str:
    """Refuse the first attempts, as the rationale rules refuse a first reason."""
    _Site.attempts += 1
    if _Site.attempts <= _REFUSED_ATTEMPTS:
        raise ModelRetry(_REFUSAL)
    ctx.deps.agent_state.operational_spec_draft.criteria.append(
        Criterion(
            id="c_tm",
            text="2 to 99 transmembrane domains",
            search_name="GenesByTransmembraneDomains",
        )
    )
    return "bound"


def _bound_transmembrane(messages: list[ModelMessage]) -> bool:
    return any(
        isinstance(part, ToolReturnPart) and part.tool_name == "bind_transmembrane"
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


def _next_call(messages: list[ModelMessage]) -> ToolCallPart:
    """Bind the signal peptide, then the transmembrane criterion, then answer."""
    if _bound_transmembrane(messages):
        return final_result_part(
            {"summary": "both criteria bound", "disposition": "spec_ready"}
        )
    name = (
        "bind_transmembrane"
        if "bind_signal_peptide" in called_tool_names(messages)
        else "bind_signal_peptide"
    )
    return ToolCallPart(tool_name=name, args="{}", tool_call_id=f"call_{name}")


@pytest.fixture
def scripted_frame(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """The FRAME pass, and the work order of every dispatch it ran."""
    _Site.attempts = 0
    orders: list[str] = []
    streamed = sub_agent_stream.stream_sub_agent

    async def _recording(*, run: PhaseRun, **kwargs: Any) -> Any:
        orders.append(run.work_order)
        return await streamed(run=run, **kwargs)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _recording)
    monkeypatch.setattr(
        sub_agent_stream, "phase_override_kwargs", lambda runtime, role: {}
    )
    toolset = FunctionToolset[AgentDeps](
        tools=[Tool(bind_signal_peptide), Tool(bind_transmembrane)],
        max_retries=_RETRIES,
    )
    with pinned_sub_agent(
        monkeypatch,
        "frame",
        model=tool_script_model(_next_call),
        toolsets=[toolset],
        instructions="Bind the criteria.",
    ):
        yield orders


def _deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt=_PROMPT))


async def test_a_pass_refused_past_its_retries_is_continued_in_one_dispatch(
    scripted_frame: list[str],
) -> None:
    deps = _deps()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("bind the criteria", deps),
        expected_criteria=2,
    )

    assert isinstance(result, FrameResult)
    assert result.disposition == "spec_ready"
    assert _Site.attempts == _REFUSED_ATTEMPTS + 1
    assert len(scripted_frame) == 2
    assert deps.frame_retried_after_stop is True
    assert deps.last_phase_stop is None
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["c_sp", "c_tm"]


async def test_the_continuation_names_the_refusal_it_continues_after(
    scripted_frame: list[str],
) -> None:
    deps = _deps()

    await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order=frame_work_order("bind the criteria", deps),
        expected_criteria=2,
    )

    assert scripted_frame[1].splitlines()[:2] == [
        (
            "FRAME work order: the previous pass stopped when bind_transmembrane "
            "refused every attempt. Continue it; this is not a fresh frame."
        ),
        f"bind_transmembrane answered: {_REFUSAL} Answer that on the first call.",
    ]
