"""A read the site does not answer fails as one tool call; the Lead's turn goes on."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic_ai import ToolFailed
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart
from pydantic_ai.tools import ToolDefinition
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.agents.tool_vocabulary import READ_ONLY_TOOLS
from pathfinder.ai.capabilities.site_reads import (
    SiteReadFailures,
    read_in_time,
    site_failure,
)
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.tools.standalone import step_ids
from pathfinder.ai.tools.standalone.results import SampledRecords
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# The 5,850-gene union of a trichdb strategy, read five genes at a time.
_UNION_STEP = 441173103
_PROMPT = "Which genes are in the result? [[arc:list-ids]]"


def _session() -> StrategySession:
    session = StrategySession(site_id="trichdb")
    session.graph = StrategyGraph(graph_id="g1", name="union", site_id="trichdb")
    session.graph.record_type = "transcript"
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_union": _UNION_STEP},
        wdk_strategy_id=330600001,
        wdk_step_tree=WDKStepTree(step_id=_UNION_STEP),
    )
    return session


def _deps() -> LeadDeps:
    bind_scripted_scope("trichdb", _PROMPT)
    return lead_deps(
        pipeline_state("trichdb", user_prompt=_PROMPT), strategy_session=_session()
    )


def _timed_out() -> WDKError:
    error = WDKError("Request failed after retries: ReadTimeout", status=502)
    error.__cause__ = httpx.ReadTimeout("")
    return error


def _refusing_read(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    async def _refuse(site_id: str, step_id: int, **kwargs: object) -> SampledRecords:
        del site_id, step_id, kwargs
        raise error

    monkeypatch.setattr(step_ids, "sample_page", _refuse)


def _returns(messages: list[ModelMessage], tool: str) -> list[tuple[str, str]]:
    return [
        (part.outcome, str(part.content))
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool
    ]


def _id_reads(messages: list[ModelMessage]) -> list[tuple[str, str]]:
    return _returns(messages, "read_step_ids")


async def test_a_read_the_site_breaks_off_leaves_the_lead_on_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _refusing_read(monkeypatch, _timed_out())
    deps = _deps()

    result = await build_lead_agent().run(_PROMPT, deps=deps, model=get_mock_model())

    assert isinstance(result.output, LeadResponse)
    assert _id_reads(result.all_messages()) == [
        (
            "failed",
            (
                "read_step_ids got no answer from the site (HTTP 502: VEuPathDB "
                "service error: Request failed after retries: ReadTimeout). Nothing "
                "was read and the strategy is unchanged. Say that the site did not "
                "answer this read, and answer from what the turn already holds."
            ),
        )
    ]
    assert deps.state.turn_markers.listings == {}


@pytest.mark.parametrize("status", [401, 403])
async def test_a_sign_in_refusal_is_no_site_failure(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """An identity refusal reaches the turn's error path, which reports it."""
    _refusing_read(monkeypatch, WDKError("login required", status=status))

    with pytest.raises(WDKError):
        await build_lead_agent().run(_PROMPT, deps=_deps(), model=get_mock_model())


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


_COMPARE_PROMPT = "How do the two counts compare? [[arc:count-comparison]]"
_NOT_ON_RECORD_TYPE = (
    'There is no search "GenesByText" associated with record type "GeneRecordClass"'
)


async def test_a_site_refusal_in_a_comparison_is_one_failed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuse(
        site_id: str, record_type: str, search_name: str, context: dict[str, str]
    ) -> list[object]:
        del site_id, record_type, search_name, context
        raise WDKError(_NOT_ON_RECORD_TYPE, status=404)

    monkeypatch.setattr(variant_comparison, "search_parameters", _refuse)
    bind_scripted_scope("plasmodb", _COMPARE_PROMPT)
    state = pipeline_state("plasmodb", user_prompt=_COMPARE_PROMPT)
    state.domain.operational_spec = OperationalSpec(goal="kinases")
    deps = lead_deps(state, strategy_session=StrategySession(site_id="plasmodb"))

    result = await build_lead_agent().run(
        _COMPARE_PROMPT, deps=deps, model=get_mock_model()
    )

    assert isinstance(result.output, LeadResponse)
    assert _returns(result.all_messages(), "compare_search_variants") == [
        (
            "failed",
            (
                "The site refused compare_search_variants (HTTP 404: VEuPathDB "
                f"service error: {_NOT_ON_RECORD_TYPE}). Nothing was read and the "
                "strategy is unchanged. Correct the arguments the site names, or "
                "say that the site refused this read."
            ),
        )
    ]


def test_the_lead_carries_the_site_read_seam_over_its_reads() -> None:
    leaves: list[AbstractCapability[Any]] = []
    build_lead_agent()._root_capability.apply(leaves.append)

    seams = [leaf for leaf in leaves if isinstance(leaf, SiteReadFailures)]

    assert len(seams) == 1
    assert {
        "read_step_ids",
        "read_gene_record",
        "get_live_strategy_state",
        "compare_search_variants",
    } <= seams[0].reads


async def test_a_read_past_its_deadline_is_one_failed_call() -> None:
    with pytest.raises(ToolFailed) as failed:
        await read_in_time(
            "get_sample_records", "step 42", asyncio.sleep(1), deadline=0.01
        )

    assert str(failed.value) == (
        "get_sample_records got no answer from the site (no answer within 0.01 s "
        "for step 42). Nothing was read and the strategy is unchanged. Say that "
        "the site did not answer this read, and answer from what the turn already "
        "holds."
    )


def test_a_connection_the_site_breaks_mid_body_is_a_site_failure() -> None:
    error = httpx.RemoteProtocolError(
        "peer closed connection without sending complete message body "
        "(incomplete chunked read)"
    )

    assert site_failure(error) is True
