"""A read the site does not answer fails as one tool call; the Lead's turn goes on."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb.errors import WDKError

from pathfinder.ai.agents.tool_vocabulary import READ_ONLY_TOOLS
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import step_ids
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.services.gene_sets.step_genes import StepIds
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# The 5,850-gene union of the trichdb run, whose five-gene read timed out.
_UNION_STEP = 441173103


def _session() -> StrategySession:
    session = StrategySession(site_id="trichdb")
    session.graph = StrategyGraph(graph_id="g1", name="union", site_id="trichdb")
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_union": _UNION_STEP}, wdk_strategy_id=330600001
    )
    return session


def _deps() -> LeadDeps:
    return lead_deps(
        pipeline_state("trichdb", user_prompt="show me five genes from it"),
        strategy_session=_session(),
    )


def _timed_out() -> WDKError:
    error = WDKError("Request failed after retries: ", status=502)
    error.__cause__ = httpx.ReadTimeout("")
    return error


def _one_read_then_text(tool_name: str, text: str) -> Callable[..., ModelResponse]:
    calls: list[int] = []

    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        calls.append(len(calls))
        if len(calls) > 1:
            return ModelResponse(parts=[TextPart(content=text)])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool_name,
                    args={"wdk_step_id": _UNION_STEP, "limit": 5},
                    tool_call_id="tc_read",
                )
            ]
        )

    return _respond


def _agent(respond: Callable[..., ModelResponse]) -> Agent[LeadDeps, str]:
    return Agent(
        FunctionModel(respond),
        deps_type=LeadDeps,
        toolsets=[FunctionToolset[LeadDeps](tools=[step_ids.read_step_ids])],
        capabilities=agent_capabilities(
            [SiteReadFailures[LeadDeps](reads=READ_ONLY_TOOLS)]
        ),
        retries=3,
    )


def _failed_returns(messages: list[ModelMessage]) -> list[str]:
    return [
        str(part.content)
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.outcome == "failed"
    ]


def _refusing_read(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    async def _refuse(
        site_id: str, wdk_step_id: int, offsets: Callable[[int], list[int]]
    ) -> StepIds:
        del site_id, wdk_step_id, offsets
        raise error

    monkeypatch.setattr(step_ids, "step_gene_ids_at", _refuse)


async def test_a_timed_out_read_fails_the_call_and_the_turn_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _refusing_read(monkeypatch, _timed_out())
    agent = _agent(_one_read_then_text("read_step_ids", "the site did not answer"))

    result = await agent.run("show me five genes from it", deps=_deps())

    assert result.output == "the site did not answer"
    assert _failed_returns(result.all_messages()) == [
        "read_step_ids got no answer from the site (HTTP 502: VEuPathDB service "
        "error: Request failed after retries: ReadTimeout). Nothing was read and "
        "the strategy is unchanged. Say that the site did not answer this read, "
        "and answer from what the turn already holds."
    ]


async def test_a_sign_in_refusal_still_ends_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No other call passes an identity refusal, so the error path reports it."""
    _refusing_read(monkeypatch, WDKError("login required", status=401))
    agent = _agent(_one_read_then_text("read_step_ids", "recovered"))

    with pytest.raises(WDKError):
        await agent.run("show me five genes from it", deps=_deps())


async def test_a_site_error_in_a_tool_that_writes_is_not_answered() -> None:
    """A write the site broke off is no read; the turn's error path owns it."""
    capability = SiteReadFailures[Any](reads=READ_ONLY_TOOLS)

    with pytest.raises(WDKError):
        await capability.on_tool_execute_error(
            MagicMock(),
            call=ToolCallPart(tool_name="delete_step", args={}, tool_call_id="tc"),
            tool_def=ToolDefinition(name="delete_step", parameters_json_schema={}),
            args={},
            error=_timed_out(),
        )


def test_the_lead_carries_the_site_read_seam_over_its_reads() -> None:
    leaves: list[AbstractCapability[Any]] = []
    build_lead_agent()._root_capability.apply(leaves.append)

    seams = [leaf for leaf in leaves if isinstance(leaf, SiteReadFailures)]

    assert len(seams) == 1
    assert {"read_step_ids", "read_gene_record", "get_live_strategy_state"} <= (
        seams[0].reads
    )
