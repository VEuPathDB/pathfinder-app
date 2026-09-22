"""How an inner tool call, its metadata and its terminal state reach the stream."""

from __future__ import annotations

from typing import Literal

from assistant_core.graph.stream_events import tool_summary_event
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.ui.vercel_ai.response_types import DataChunk, TextStartChunk

from pathfinder.ai.capabilities.error_classification import build_error_directive
from pathfinder.ai.lead.sub_agent_events import (
    _forward_inner_event,
    _read_tool_metadata,
)
from pathfinder.tests.unit.ai.lead.conftest import ChunkCollector

_PARENT = "sa_1"
_INNER = "s1"
_RETRY_TEXT = "Unknown search 'GenesByGOTerm'. Call get_search_overview first."

InnerEvent = FunctionToolCallEvent | FunctionToolResultEvent


def _forward(*events: InnerEvent) -> ChunkCollector:
    collector = ChunkCollector()
    inner_calls: dict[str, str] = {}
    for event in events:
        _forward_inner_event(
            parent_tool_call_id=_PARENT,
            writer=collector,
            inner_calls=inner_calls,
            event=event,
        )
    return collector


def _results(collector: ChunkCollector) -> list[dict[str, object]]:
    return [
        data
        for data in collector.data_of("data-sub-agent-step")
        if data.get("resultSummary") is not None
    ]


def _summaries(collector: ChunkCollector) -> list[str]:
    return [str(data["resultSummary"]) for data in _results(collector)]


def _states(collector: ChunkCollector) -> list[str]:
    return [str(data["state"]) for data in _results(collector)]


def _call(tool_name: str, tool_call_id: str = _INNER) -> FunctionToolCallEvent:
    return FunctionToolCallEvent(
        part=ToolCallPart(tool_name=tool_name, tool_call_id=tool_call_id),
    )


def test_string_retry_surfaces_real_message() -> None:
    collector = _forward(
        _call("set_criterion", "c1"),
        FunctionToolResultEvent(
            part=RetryPromptPart(
                content=_RETRY_TEXT,
                tool_name="set_criterion",
                tool_call_id="c1",
            ),
        ),
    )

    summaries = _summaries(collector)
    assert summaries == [_RETRY_TEXT]
    assert all("retry requested" not in s for s in summaries)


def test_structured_validation_retry_is_rendered() -> None:
    collector = _forward(
        _call("build_plan", "c2"),
        FunctionToolResultEvent(
            part=RetryPromptPart(
                content=[
                    {
                        "type": "missing",
                        "loc": ("steps", 0, "search_name"),
                        "msg": "Field required",
                        "input": {},
                    },
                ],
                tool_name="build_plan",
                tool_call_id="c2",
            ),
        ),
    )

    summaries = _summaries(collector)
    assert summaries
    joined = " ".join(summaries)
    assert "retry requested" not in joined
    assert (
        "search_name" in joined or "Field required" in joined or "validation" in joined
    )


def _drive_part(
    part: ToolReturnPart | RetryPromptPart,
    tool_name: str = "get_search_overview",
) -> list[str]:
    return _states(
        _forward(_call(tool_name, "c1"), FunctionToolResultEvent(part=part)),
    )


def _drive(
    result_content: object,
    tool_name: str = "get_search_overview",
    outcome: Literal["success", "denied"] = "success",
) -> list[str]:
    return _drive_part(
        ToolReturnPart(
            content=result_content,
            tool_name=tool_name,
            tool_call_id="c1",
            outcome=outcome,
        ),
        tool_name,
    )


def test_returned_error_directive_renders_as_failed() -> None:
    directive = build_error_directive(
        error_type="SEARCH_NOT_FOUND",
        tool_name="get_search_overview",
        tool_args={"search_name": "GenesByRNASeqMadeUp"},
        detail="VEuPathDB service error: HTTP 404",
        next_actions=["Call search_for_searches(...)"],
        do_not="Do not retry with the same search name",
    )
    assert _drive(directive) == ["failed"]


def test_normal_result_still_renders_as_completed() -> None:
    assert _drive(
        {"search_name": "GenesByText", "display_name": "Gene Text Search"}
    ) == ["completed"]


def test_denied_call_renders_as_denied() -> None:
    assert _drive("The tool call was denied.", outcome="denied") == ["denied"]


def test_retry_prompt_renders_as_failed() -> None:
    assert _drive_part(
        RetryPromptPart(
            content="search_name is not a known search",
            tool_name="get_search_overview",
            tool_call_id="c1",
        ),
    ) == ["failed"]


def test_forwards_data_chunks() -> None:
    read = _read_tool_metadata(
        [DataChunk(type="data-plan-artifact", data={"planId": "p1"})],
    )
    assert len(read.forwarded) == 1
    assert read.forwarded[0].type == "data-plan-artifact"
    assert read.summary is None


def test_drops_non_streamable_chunks() -> None:
    read = _read_tool_metadata([TextStartChunk(id="x")])
    assert read.forwarded == []


def test_ignores_non_list_metadata() -> None:
    assert _read_tool_metadata(None).forwarded == []
    assert _read_tool_metadata("not a list").forwarded == []


def test_a_tool_summary_is_lifted_and_never_forwarded() -> None:
    """The inner call id names no part on the main stream, so the chunk stays out."""
    read = _read_tool_metadata(
        [
            DataChunk(
                type="data-tool-summary",
                data={"toolCallId": "s1", "summary": "12 searches", "status": "ok"},
            ),
            DataChunk(type="data-graph-snapshot", data={"steps": []}),
        ],
    )
    assert read.summary == "12 searches"
    assert [chunk.type for chunk in read.forwarded] == ["data-graph-snapshot"]


def _with_metadata(metadata: list[object]) -> ChunkCollector:
    return _forward(
        FunctionToolCallEvent(
            part=ToolCallPart(
                tool_name="search_for_searches",
                args={"query": "heat shock"},
                tool_call_id=_INNER,
            ),
        ),
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="search_for_searches",
                content={"total": 12},
                tool_call_id=_INNER,
                metadata=metadata,
            ),
        ),
    )


def _completed(collector: ChunkCollector) -> list[dict[str, object]]:
    return [
        data
        for data in collector.data_of("data-sub-agent-step")
        if data["state"] == "completed"
    ]


def test_the_inner_line_becomes_the_step_text() -> None:
    collector = _with_metadata(
        [tool_summary_event(tool_call_id=_INNER, summary="12 searches")],
    )

    completed = _completed(collector)
    assert len(completed) == 1
    assert completed[0]["resultSummary"] == "12 searches"


def test_no_summary_chunk_names_an_inner_call() -> None:
    collector = _with_metadata(
        [tool_summary_event(tool_call_id=_INNER, summary="12 searches")],
    )

    assert collector.chunks_of("data-tool-summary") == []


def test_a_figure_beside_the_summary_still_reaches_the_stream() -> None:
    collector = _with_metadata(
        [
            DataChunk(type="data-graph-snapshot", data={"steps": []}),
            tool_summary_event(tool_call_id=_INNER, summary="12 searches"),
        ],
    )

    assert [
        chunk["type"]
        for chunk in collector.chunks
        if str(chunk["type"]).startswith("data-graph")
    ] == ["data-graph-snapshot"]


def test_the_json_dump_is_the_fallback_when_the_tool_wrote_no_line() -> None:
    completed = _completed(_with_metadata([]))

    assert completed[0]["resultSummary"] == '{"total": 12}'


def _completed_step(content: object) -> dict[str, object]:
    collector = _forward(
        _call("get_search_overview"),
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="get_search_overview", content=content, tool_call_id=_INNER
            ),
        ),
    )
    return _completed(collector)[0]


def _result_of(content: object) -> object:
    return _completed_step(content)["result"]


def test_a_completed_step_carries_its_return_as_json() -> None:
    """The raw trace shows a sub-agent step's return the way it shows the Lead's."""
    assert _result_of({"search_name": "GenesByText", "count": 3}) == {
        "search_name": "GenesByText",
        "count": 3,
    }


def test_a_return_over_the_cap_is_cut_with_a_marker() -> None:
    result = _result_of({"ids": "x" * 20_000})
    assert isinstance(result, str)
    assert result.endswith("... (truncated)")
    assert len(result) < 20_000


def test_a_return_that_cannot_be_serialised_carries_no_result() -> None:
    step = _completed_step(object())

    assert {key: step[key] for key in ("state", "toolName", "result")} == {
        "state": "completed",
        "toolName": "get_search_overview",
        "result": None,
    }
