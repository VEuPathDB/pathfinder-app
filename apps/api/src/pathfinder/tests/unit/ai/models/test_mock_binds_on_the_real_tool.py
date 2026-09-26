"""The mock FRAME's transform bindings are accepted by the real ``set_criterion``
on a definition toxodb published."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.models._mock_pins import edit_order
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_params,
    serve_site_listing,
)

_ORTHOLOGS = suite_search("search_genes_by_orthologs_toxodb")
_BOUND = {
    "round-trip": ["orthologs_there", "orthologs_back"],
    "orthologs": ["orthologs"],
}


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_ORTHOLOGS])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_ORTHOLOGS.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _state() -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_orthology",
            tool="search_for_searches",
            record_type="transcript",
            query="",
            hits=[
                CatalogHit(
                    name="GenesByOrthologs",
                    display_name=_ORTHOLOGS.display_name,
                    record_type="transcript",
                )
            ],
        )
    )
    return state


async def _answer(state: AgentToolState, call: ToolCallPart) -> object:
    args = call.args_as_dict()
    if call.tool_name != "set_criterion":
        return "ok"
    why = args.get("why")
    returned = await set_criterion(
        frame_ctx(state),
        criterion_id=args["criterion_id"],
        text=args["text"],
        search_name=args["search_name"],
        role=args["role"],
        params=args.get("params"),
        why=None if why is None else SearchChoice.model_validate(why),
    )
    return returned.return_value


async def _played() -> list[ToolCallPart]:
    state = _state()
    script = role_script("frame")
    order = edit_order("toxodb")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content=order)]
    calls: list[ToolCallPart] = []
    for _ in range(30):
        pinned = pinned_frame_sheets(frame_ctx(state)) or ""
        messages.append(ModelRequest(parts=parts, instructions=pinned))
        call = script(messages)
        calls.append(call)
        if call.tool_name in {"final_result", "set_structure"}:
            break
        messages.append(ModelResponse(parts=[call]))
        try:
            answer = await _answer(state, call)
            reply: ToolReturnPart | RetryPromptPart = ToolReturnPart(
                tool_name=call.tool_name, content=answer, tool_call_id=call.tool_call_id
            )
        except ModelRetry as refused:
            reply = RetryPromptPart(
                content=refused.message,
                tool_name=call.tool_name,
                tool_call_id=call.tool_call_id,
            )
        parts = [reply]
    return calls


@pytest.mark.parametrize("arc", ["round-trip", "orthologs"])
async def test_the_transforms_bind_on_the_real_tool(
    monkeypatch: pytest.MonkeyPatch, arc: str
) -> None:
    _serve(monkeypatch)
    bind_scripted_scope("toxodb", f"Keep them [[arc:{arc}]]")

    calls = await _played()

    bound = [
        c.args_as_dict()["criterion_id"]
        for c in calls
        if c.tool_name == "set_criterion" and "params" in c.args_as_dict()
    ]
    assert calls[-1].tool_name == "set_structure"
    assert bound == _BOUND[arc]
