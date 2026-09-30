"""The muris-phrase arc binds on the real ``set_criterion`` over the sheets
giardiadb published and answered under the bound values: the text keeps its
phrase reading, and the organism the message names one letter off is stated."""

from __future__ import annotations

from collections.abc import Mapping

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
from veupathdb.domain.parameters import ParamValue
from veupathdb.wdk import SiteSearchResponse
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.phrase_label_arcs import PHRASE, TEXT
from pathfinder.ai.tools.standalone import _frame_count, frame_spec
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.caveats import phrase_caveats
from pathfinder.tests._support.recorded_counts import (
    serve_counts,
    serve_site_search,
    wire,
)
from pathfinder.tests._support.recorded_searches import serve_recorded, suite_search
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_site_listing,
)

_PUBLISHED = suite_search("search_giardiadb_genes_by_text")
_UNDER_CONTEXT = suite_search("search_giardiadb_genes_by_text_under_context")
_MESSAGE = (
    "Giardia muris Roberts-Thompson genes with a cysteine-rich protein annotation. "
    "[[arc:muris-phrase]]"
)
# GiardiaDB GenesByText over product, Products and Notes in G. muris, read live.
_WORDS, _PHRASE = 4497, 0


def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
    return _PHRASE if wire(params, "text_expression").startswith('"') else _WORDS


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_PUBLISHED])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
            read = _UNDER_CONTEXT if context else _PUBLISHED
            return format_param_info_typed(list(read.parameters or []))

        return fetch_at

    async def _bound_count(*_args: object, **_kwargs: object) -> int:
        return _WORDS

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_count, "count_bound_criterion", _bound_count)
    no_validation(monkeypatch)
    serve_site_listing(monkeypatch, [])
    serve_counts(monkeypatch, _count)
    serve_site_search(monkeypatch, SiteSearchResponse())


def _state() -> AgentToolState:
    state = AgentToolState()
    state.request_messages = [_MESSAGE]
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_text",
            tool="search_for_searches",
            record_type="transcript",
            query=_MESSAGE,
            hits=[
                CatalogHit(
                    name=TEXT,
                    display_name=_PUBLISHED.display_name,
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


async def _framed(monkeypatch: pytest.MonkeyPatch) -> AgentToolState:
    _serve(monkeypatch)
    bind_scripted_scope("giardiadb", _MESSAGE)
    state = _state()
    script = role_script("frame")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content=_MESSAGE)]
    for _ in range(30):
        pinned = pinned_frame_sheets(frame_ctx(state)) or ""
        messages.append(ModelRequest(parts=parts, instructions=pinned))
        call = script(messages)
        if call.tool_name in {"final_result", "set_structure"}:
            break
        messages.append(ModelResponse(parts=[call]))
        try:
            reply: ToolReturnPart | RetryPromptPart = ToolReturnPart(
                tool_name=call.tool_name,
                content=await _answer(state, call),
                tool_call_id=call.tool_call_id,
            )
        except ModelRetry as refused:
            reply = RetryPromptPart(
                content=refused.message,
                tool_name=call.tool_name,
                tool_call_id=call.tool_call_id,
            )
        parts = [reply]
    return state


async def test_the_muris_arc_keeps_the_phrase_reading_and_states_the_organism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _framed(monkeypatch)

    [criterion] = state.operational_spec_draft.criteria
    sources = {name: held.source for name, held in criterion.resolved_params.items()}
    assert (sources["text_search_organism"], sources["text_expression"]) == (
        "stated",
        "stated",
    )
    [caveat] = phrase_caveats(state.operational_spec_draft)
    assert (caveat.value, caveat.words_count, caveat.phrase_count) == (
        PHRASE,
        _WORDS,
        _PHRASE,
    )
