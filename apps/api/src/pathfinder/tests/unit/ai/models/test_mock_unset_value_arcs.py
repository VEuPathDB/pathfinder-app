"""The unset-value arcs bind on the real ``set_criterion`` over the sheets
plasmodb published: the radio-off value binds no text query and is the site's,
the species the message names by its label is stated, a read-only value is the
site's, and an organism a text step shares is not held to the records."""

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
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import SIGNAL_PEPTIDE
from pathfinder.ai.models.mock.unset_value_arcs import (
    INTERPRO,
    ORTHOLOG_PATTERN,
    TEXT,
    radio_off_domain_spec,
)
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.catalog_discovery import get_parameter_options
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.evidence import (
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.shown_requirements import TextQuery, held_to_the_records
from pathfinder.services.strategies.text_queries import text_query_criteria
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

_SHEETS: dict[str, WDKSearch] = {
    INTERPRO: suite_search("search_genes_by_interpro_domain"),
    ORTHOLOG_PATTERN: suite_search("search_genes_by_ortholog_pattern"),
    TEXT: suite_search("search_genes_by_text"),
    SIGNAL_PEPTIDE: suite_search("search_genes_with_signal_peptide"),
}
_ORGANISM = SiteValues.for_site("plasmodb").organism
_DOMAIN_MESSAGE = (
    f"{_ORGANISM} genes with a Plasmodium-specific domain that have no ortholog "
    "in Homo sapiens. [[arc:radio-off-domain]]"
)
_GPI_MESSAGE = (
    f"{_ORGANISM} genes whose gene product description names a GPI anchor, or "
    "with a signal peptide. [[arc:text-beside-organism]]"
)


def _serve(monkeypatch: pytest.MonkeyPatch, asked: list[str]) -> None:
    serve_recorded(monkeypatch, list(_SHEETS.values()))

    def _params(_context: dict[str, str]) -> list[ParameterInfo]:
        return format_param_info_typed(_SHEETS[asked[-1]].parameters or [])

    serve_params(monkeypatch, _params)
    serve_options_reads(
        monkeypatch,
        lambda name: format_param_info_typed(_SHEETS[name].parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _state(message: str) -> AgentToolState:
    state = AgentToolState()
    state.request_messages = [message]
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_domains",
            tool="search_for_searches",
            record_type="transcript",
            query=message,
            hits=[
                CatalogHit(
                    name=name, display_name=sheet.display_name, record_type="transcript"
                )
                for name, sheet in _SHEETS.items()
            ],
        )
    )
    return state


async def _answer(
    state: AgentToolState, call: ToolCallPart, asked: list[str]
) -> object:
    args = call.args_as_dict()
    if call.tool_name == "get_parameter_options":
        read = await get_parameter_options(frame_ctx(state), **args)
        return read.return_value
    if call.tool_name != "set_criterion":
        return "ok"
    asked.append(args["search_name"])
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
    monkeypatch: pytest.MonkeyPatch, message: str
) -> tuple[AgentToolState, list[ToolCallPart]]:
    asked: list[str] = []
    _serve(monkeypatch, asked)
    bind_scripted_scope("plasmodb", message)
    state = _state(message)
    script = role_script("frame")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content=message)]
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
            answer = await _answer(state, call, asked)
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
    return state, calls


def _sources(state: AgentToolState, names: set[str]) -> dict[tuple[str, str], str]:
    return {
        (criterion.id, name): held.source
        for criterion in state.operational_spec_draft.criteria
        for name, held in criterion.resolved_params.items()
        if name in names
    }


async def test_the_radio_off_domain_arc_binds_what_the_site_and_the_message_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, calls = await _framed(monkeypatch, _DOMAIN_MESSAGE)

    assert calls[-1].tool_name == "set_structure"
    assert _sources(
        state, {"domain_accession", "excluded_species", "included_species"}
    ) == {
        ("specific_domain", "domain_accession"): "default",
        ("no_human_ortholog", "excluded_species"): "stated",
        ("no_human_ortholog", "included_species"): "default",
    }
    assert text_query_criteria(state.operational_spec_draft, _SHEETS) == []


async def test_the_text_beside_organism_arc_holds_no_organism_row_to_the_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, calls = await _framed(monkeypatch, _GPI_MESSAGE)
    queries = text_query_criteria(state.operational_spec_draft, _SHEETS)
    organism_row = RequirementCheck(
        text=_ORGANISM,
        turn=1,
        answered_by=["gpi_text", "signal_peptide"],
        how="parameter",
        status="met",
        note="both steps bind the organism",
    )
    review = VerificationReview(
        requirements=[organism_row],
        sampled_genes=[
            SampledGene(
                gene_id="PF3D7_0100100",
                product="erythrocyte membrane protein 1",
                organism=_ORGANISM,
                fits="no",
                why="the record names no GPI anchor",
            )
        ],
    )

    assert calls[-1].tool_name == "set_structure"
    assert _sources(state, {"document_type"}) == {
        ("gpi_text", "document_type"): "default"
    }
    assert queries == [
        TextQuery(criterion_id="gpi_text", param="text_expression", value="GPI anchor")
    ]
    assert held_to_the_records(review, queries) == review


def test_the_arc_frames_the_two_criteria_it_names() -> None:
    plan = radio_off_domain_spec(SiteValues.for_site("plasmodb"))

    assert [(c.criterion_id, c.search_name) for c in plan.criteria] == [
        ("specific_domain", INTERPRO),
        ("no_human_ortholog", ORTHOLOG_PATTERN),
    ]
