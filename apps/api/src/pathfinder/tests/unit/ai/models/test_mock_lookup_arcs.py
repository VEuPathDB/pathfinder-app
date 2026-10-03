"""The odorant-binding arc binds on the real ``set_criterion``: the family it
picks with no lookup is refused, the lookup reaches the OBP family, and the
facts row names the lookup and its matches."""

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
from veupathdb.domain.parameters import MultiPickValue, VocabOption
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.lookup_arcs import (
    AEDES,
    CSP_FAMILY,
    DOMAINS,
    INTERPRO,
    OBP_FAMILY,
    OBP_PHRASINGS,
)
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.catalog_discovery import get_parameter_options
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.measurement_clauses import read_pick_clauses
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.options_reads import serve_options_reads
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_params,
    serve_site_listing,
)

_DEFINITION = suite_search("search_genes_by_interpro_domain")
_MESSAGE = (
    f"Find {AEDES} odorant-binding protein genes on chromosome 3. "
    "[[arc:odorant-lookup]]"
)
# The Aedes domain entries whose labels hold an odorant or pheromone word.
_AEDES_DOMAINS = [
    VocabOption(value="PF02949", display="PF02949 : 7tm Odorant receptor"),
    VocabOption(
        value=OBP_FAMILY,
        display=f"{OBP_FAMILY} : Pheromone/general odorant binding protein",
    ),
    VocabOption(
        value=CSP_FAMILY,
        display=f"{CSP_FAMILY} : Insect pheromone-binding family, A10/OS-D",
    ),
    VocabOption(value="PF22651", display="PF22651 : AgamOBP47-like"),
    VocabOption(value="PF14778", display="PF14778 : Odorant response abnormal 4-like"),
]


def _aedes_sheet() -> list[ParameterInfo]:
    """The recorded sheet, with the Aedes organism and its domain entries."""
    replaced = {
        "organism": [VocabOption(value=AEDES, display=AEDES)],
        DOMAINS: _AEDES_DOMAINS,
    }
    return [
        info.model_copy(
            update={"allowed_values": replaced[info.name], "vocab_leaves": []}
        )
        if info.name in replaced
        else info
        for info in format_param_info_typed(_DEFINITION.parameters or [])
    ]


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_DEFINITION])
    serve_params(monkeypatch, lambda _context: _aedes_sheet())
    serve_options_reads(monkeypatch, lambda _name: _aedes_sheet())
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


async def _answer(state: AgentToolState, call: ToolCallPart) -> object:
    args = call.args_as_dict()
    if call.tool_name == "get_parameter_options":
        return (await get_parameter_options(frame_ctx(state), **args)).return_value
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


async def _framed(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AgentToolState, list[ToolCallPart], list[str]]:
    _serve(monkeypatch)
    bind_scripted_scope("vectorbase", _MESSAGE)
    state = AgentToolState()
    state.request_messages = [_MESSAGE]
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_domains",
            tool="search_for_searches",
            record_type="transcript",
            query=_MESSAGE,
            hits=[
                CatalogHit(
                    name=INTERPRO,
                    display_name=_DEFINITION.display_name,
                    record_type="transcript",
                )
            ],
        )
    )
    script = role_script("frame")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content=_MESSAGE)]
    calls: list[ToolCallPart] = []
    refusals: list[str] = []
    for _ in range(20):
        pinned = pinned_frame_sheets(frame_ctx(state)) or ""
        messages.append(ModelRequest(parts=parts, instructions=pinned))
        call = script(messages)
        calls.append(call)
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
            refusals.append(refused.message)
            reply = RetryPromptPart(
                content=refused.message,
                tool_name=call.tool_name,
                tool_call_id=call.tool_call_id,
            )
        parts = [reply]
    return state, calls, refusals


def _obp(state: AgentToolState) -> Criterion:
    return next(c for c in state.operational_spec_draft.criteria if c.id == "c_obp")


async def test_the_pick_no_lookup_read_is_refused_and_the_lookup_reaches_obp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, calls, refusals = await _framed(monkeypatch)
    lookups = [
        c.args_as_dict() for c in calls if c.tool_name == "get_parameter_options"
    ]

    assert calls[-1].tool_name == "set_structure"
    assert [r.split(" holds ")[0] for r in refusals] == [
        f"{DOMAINS} (Specific Domain(s)) on {INTERPRO}"
    ]
    assert [(a["parameter_id"], a["query"]) for a in lookups] == [
        (DOMAINS, OBP_PHRASINGS)
    ]
    assert _obp(state).resolved_params[DOMAINS].value == MultiPickValue(
        values=[OBP_FAMILY]
    )


async def test_the_facts_row_names_the_lookup_and_its_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _calls, _refusals = await _framed(monkeypatch)

    assert read_pick_clauses(_obp(state), DOMAINS, noun="gene") == [
        (
            "Specific Domain(s) took 1 of the 2 entries that match "
            "'odorant binding', 'OBP', 'PBP/GOBP'"
        )
    ]
