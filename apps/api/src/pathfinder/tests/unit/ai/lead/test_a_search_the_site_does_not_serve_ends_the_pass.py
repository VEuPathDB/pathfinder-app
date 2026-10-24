from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from veupathdb.domain.parameters import InputDatasetValue, StringValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_stream
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.dispatch_messages import stop_heading
from pathfinder.ai.lead.phase_stop import PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import PhaseRun, stream_sub_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.toolsets.frame import build_toolset
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.orthomcl_site import TYPED_GENE_ID, OrthoSite
from pathfinder.tests._support.record_classes import list_searches_under
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_part,
    lead_deps,
    pipeline_state,
    tool_script_model,
)
from pathfinder.tests.unit.ai.tools._orthomcl_site import (
    group_strategy_session,
    serve_orthomcl,
)

pytestmark = pytest.mark.usefixtures("collector")

_PROMPT = (
    f"Look the protein up by its ID {TYPED_GENE_ID} and give me its ortholog group."
)
_NOT_SERVED = (
    "The search ByAccession is not served by orthomcl under group (HTTP 404: "
    'There is no search "ByAccession" associated with record type '
    '"GroupRecordClass").'
)
_WHY = {
    "ByIdList": {
        "basis": "only_match",
        "term": "ByIdList",
        "reason": "ByIdList finds proteins by a VEuPathDB gene id",
    },
    "ByAccession": {
        "basis": "parameter",
        "term": "Accession",
        "reason": "Accession takes the protein name the request states",
    },
}

type Script = Callable[[list[ModelMessage]], ToolCallPart]


def _call(
    step: int,
    search_name: str,
    params: dict[str, Any] | None,
    criterion_id: str = "c_protein",
) -> ToolCallPart:
    args: dict[str, Any] = {
        "criterion_id": criterion_id,
        "text": f"the protein {TYPED_GENE_ID}",
        "search_name": search_name,
        "role": "seed",
    }
    if params is not None:
        args |= {"params": params, "why": _WHY[search_name]}
    return ToolCallPart(
        tool_name="set_criterion", args=args, tool_call_id=f"call_{step}"
    )


def _answers(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(part, ToolReturnPart | RetryPromptPart)
        and part.tool_name == "set_criterion"
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


def _scripted(*calls: ToolCallPart) -> Script:
    def _next(messages: list[ModelMessage]) -> ToolCallPart:
        step = _answers(messages)
        if step < len(calls):
            return calls[step]
        return final_result_part(
            {"summary": "c_protein binds ByIdList", "disposition": "spec_ready"}
        )

    return _next


_WRONG_THEN_RIGHT = _scripted(
    _call(0, "ByAccession", {"accession": TYPED_GENE_ID}),
    _call(1, "ByIdList", {"source_ids": TYPED_GENE_ID}),
)


_NAMED: list[str] = []


def _always_wrong(messages: list[ModelMessage]) -> ToolCallPart:
    step = _answers(messages)
    _NAMED.append(f"call_{step}")
    return _call(step, "ByAccession", {"accession": TYPED_GENE_ID}, f"c_protein_{step}")


def _wrong_between_sheets(messages: list[ModelMessage]) -> ToolCallPart:
    step = _answers(messages)
    if step % 2:
        return _call(step, "ByIdList", None)
    return _call(step, "ByAccession", {"accession": TYPED_GENE_ID}, f"c_protein_{step}")


def _deps() -> LeadDeps:
    return lead_deps(
        pipeline_state(site_id="orthomcl", user_prompt=_PROMPT),
        strategy_session=group_strategy_session(),
    )


def _agent_deps(deps: LeadDeps, accession_under: str) -> AgentDeps:
    agent_deps = agent_deps_for(deps, call_id="call_test")
    state: AgentToolState = agent_deps.agent_state
    state.request_messages = [_PROMPT]
    state.record_catalog_read(listing(["ByIdList"], record_type="sequence"))
    state.record_catalog_read(
        listing(["ByAccession"], record_type=accession_under, tool_call_id="call_2")
    )
    return agent_deps


@pytest.fixture
def qa_listing(monkeypatch: pytest.MonkeyPatch) -> OrthoSite:
    monkeypatch.setattr(
        sub_agent_stream, "phase_override_kwargs", lambda runtime, role: {}
    )
    return serve_orthomcl(monkeypatch)


@pytest.fixture
def stale_catalog(qa_listing: OrthoSite, monkeypatch: pytest.MonkeyPatch) -> OrthoSite:
    list_searches_under(monkeypatch, "group", ["ByAccession"])
    return qa_listing


@pytest.fixture
def scripted(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Script], AbstractContextManager[None]]:
    def _pin(script: Script) -> AbstractContextManager[None]:
        return pinned_sub_agent(
            monkeypatch,
            "frame",
            model=tool_script_model(script),
            toolsets=[build_toolset()],
            instructions="Bind the criteria.",
        )

    return _pin


async def _frame(deps: LeadDeps, agent_deps: AgentDeps) -> FrameResult | None:
    result = await stream_sub_agent(
        run=PhaseRun("frame", "bind the protein", 1),
        agent_deps=agent_deps,
        parent_tool_call_id="call_frame_1",
        expected_output_type=FrameResult,
        deps=deps,
    )
    assert result is None or isinstance(result, FrameResult)
    return result


async def test_a_name_search_that_counts_nothing_gives_way_to_the_id_search(
    qa_listing: OrthoSite, scripted: Callable[[Script], AbstractContextManager[None]]
) -> None:
    deps = _deps()
    agent_deps = _agent_deps(deps, "sequence")

    with scripted(_WRONG_THEN_RIGHT):
        result = await _frame(deps, agent_deps)

    assert result is not None
    assert result.disposition == "spec_ready"
    assert qa_listing.counted == [
        ("ByAccession", {"accession": StringValue(value=TYPED_GENE_ID)}),
        ("ByIdList", {"source_ids": InputDatasetValue(dataset_id="9001")}),
    ]
    assert all(read[0] == "sequence" for read in qa_listing.reads)
    [criterion] = agent_deps.agent_state.operational_spec_draft.criteria
    assert (criterion.id, criterion.search_name) == ("c_protein", "ByIdList")


async def test_a_pass_that_tries_a_search_the_site_does_not_serve_then_binds(
    stale_catalog: OrthoSite,
    scripted: Callable[[Script], AbstractContextManager[None]],
) -> None:
    deps = _deps()
    agent_deps = _agent_deps(deps, "group")

    with scripted(_WRONG_THEN_RIGHT):
        result = await _frame(deps, agent_deps)

    assert result is not None
    assert result.disposition == "spec_ready"
    assert deps.last_phase_stop is None
    assert stale_catalog.reads.count(("group", "ByAccession")) == 1
    assert ("group", "ByIdList") not in stale_catalog.reads
    assert stale_catalog.datasets == [[TYPED_GENE_ID]]
    [criterion] = agent_deps.agent_state.operational_spec_draft.criteria
    assert (criterion.id, criterion.search_name) == ("c_protein", "ByIdList")


async def test_a_pass_that_keeps_naming_it_stops_on_the_search_not_served(
    stale_catalog: OrthoSite,
    scripted: Callable[[Script], AbstractContextManager[None]],
) -> None:
    deps = _deps()
    _NAMED.clear()

    with scripted(_always_wrong):
        result = await _frame(deps, _agent_deps(deps, "group"))

    assert result is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert stop.reason is PhaseStopReason.SEARCH_NOT_SERVED
    assert stop.tool_name == "set_criterion"
    assert stop.refusal == (
        f"{_NOT_SERVED} This pass named a search the site does not serve 4 times "
        "and stops here."
    )
    assert stop_heading(stop) == (
        "the previous pass stopped on a search the site does not serve"
    )
    assert _NAMED == ["call_0", "call_1", "call_2", "call_3"]
    assert stale_catalog.reads == [("group", "ByAccession")]


async def test_a_pass_that_names_it_between_other_binds_stops_the_same_way(
    stale_catalog: OrthoSite,
    scripted: Callable[[Script], AbstractContextManager[None]],
) -> None:
    deps = _deps()

    with scripted(_wrong_between_sheets):
        result = await _frame(deps, _agent_deps(deps, "group"))

    assert result is None
    stop = deps.last_phase_stop
    assert stop is not None
    assert stop.reason is PhaseStopReason.SEARCH_NOT_SERVED
    assert stop.refusal.startswith(_NOT_SERVED)
    assert stale_catalog.reads.count(("group", "ByAccession")) == 1
