"""The consult arc asks the organism only when the real ``set_criterion`` opens
it as a slot on the recorded signal peptide search, and offers the values the
sheet lists for it, the site organism recommended."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import (
    pinned_frame_sheets,
    pinned_frame_workspace,
)
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionReply
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    serve_recorded_definitions,
    suite_search,
)
from pathfinder.tests.unit.ai.models._mock_turns import seen_by_the_model
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_site_listing,
)

_SIGNAL = suite_search("search_genes_with_signal_peptide")


class _Question(CamelModel):
    question: str
    recommended_value: str
    options: list[str]


class _Asked(CamelModel):
    model_config = ConfigDict(extra="ignore")

    open_questions: list[_Question]


_OPEN = "organism"


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_SIGNAL])
    serve_recorded_definitions(monkeypatch, [_SIGNAL])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return format_param_info_typed(_SIGNAL.parameters or [])

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=[]))


async def _answer(state: AgentToolState, call: ToolCallPart) -> object:
    args = call.args_as_dict()
    match call.tool_name:
        case "list_searches":
            state.record_catalog_read(listing([_SIGNAL.url_segment]))
            return [{"name": _SIGNAL.url_segment}]
        case "set_criterion":
            why = args.get("why")
            bound = await set_criterion(
                frame_ctx(state),
                criterion_id=args["criterion_id"],
                text=args["text"],
                search_name=args["search_name"],
                role=args["role"],
                params=args.get("params"),
                why=None if why is None else SearchChoice.model_validate(why),
            )
            return bound.return_value
        case _:
            return "ok"


async def _played() -> tuple[list[object], dict[str, object]]:
    """Every ``set_criterion`` answer of the first pass, and its final result."""
    state = AgentToolState()
    script = role_script("frame")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content="Frame work order")]
    answers: list[object] = []
    for _ in range(12):
        ctx = frame_ctx(state)
        pinned = "\n\n".join(
            b for b in (pinned_frame_sheets(ctx), pinned_frame_workspace(ctx)) if b
        )
        messages.append(ModelRequest(parts=parts, instructions=pinned))
        call = script(seen_by_the_model(messages))
        if call.tool_name == "final_result":
            return answers, call.args_as_dict()
        answer = await _answer(state, call)
        if call.tool_name == "set_criterion":
            answers.append(answer)
        messages.append(ModelResponse(parts=[call]))
        parts = [
            ToolReturnPart(
                tool_name=call.tool_name, content=answer, tool_call_id=call.tool_call_id
            )
        ]
    msg = "the pass never answered"
    raise AssertionError(msg)


async def test_the_question_offers_the_sheet_values_of_the_slot_the_tool_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    bind_scripted_scope("plasmodb", "Find drug targets [[arc:consult]]")

    answers, result = await _played()
    slots = [
        slot
        for answer in answers
        for slot in CriterionReply.model_validate(answer).open_slots
        if slot.param_name == _OPEN
    ]
    [question] = _Asked.model_validate(result).open_questions

    published = [
        option.value
        for info in format_param_info_typed(_SIGNAL.parameters or [])
        if info.name == _OPEN
        for option in info.vocabulary()
    ]
    organism = SiteValues.for_site("plasmodb").organism

    assert len(slots) == 1
    assert len(slots[0].options) > 1
    assert set(slots[0].options) <= {*published}
    assert question.recommended_value == organism
    assert (
        question.options
        == [
            organism,
            *(v for v in published if v.split()[0] == "Plasmodium" and v != organism),
        ][:8]
    )
