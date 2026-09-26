"""The mock FRAME's own-hit binding of the other-site arc is accepted by the real
``set_criterion``, on recorded definitions the real ``search_for_searches`` ranked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

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
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    SearchMatch,
    format_param_info_typed,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import (
    pinned_frame_sheets,
    pinned_frame_workspace,
)
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.models._mock_turns import seen_by_the_model
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE, match
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    serve_no_other_sites,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_site_listing,
)

_SIGNAL = suite_search("search_genes_with_signal_peptide")
_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_SENSE_ANTISENSE = suite_search("search_genes_by_rnaseq_cqui_blood_fed_sense_antisense")
_FOLD_CHANGE = suite_search("search_genes_by_microarray_aaeg_blood_meal_fold_change")
_LISTED = (_SIGNAL, _PERCENTILE)
# The searches every answer carries, whatever it ranked.
_UNIVERSAL = [
    suite_search("search_genes_by_text"),
    suite_search("search_genes_by_taxon"),
]
_WORDS = "genes that carry a secretory signal peptide"
_TERM = "genes that carry a secretory signal"


def _ranked(definition: WDKSearch) -> list[SearchMatch]:
    """``definition`` ranked nearest, above a recorded search that scores less."""
    hit = match(
        definition.url_segment, definition.display_name, definition.description, 0.52
    )
    sibling = _SIGNAL if definition is not _SIGNAL else _PERCENTILE
    below = match(sibling.url_segment, sibling.display_name, sibling.description, 0.41)
    return [below, hit]


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    definition: WDKSearch,
    ranked: list[SearchMatch] | None = None,
) -> None:
    ranked = _ranked(definition) if ranked is None else ranked
    served = [definition, *_UNIVERSAL, _SIGNAL, _PERCENTILE]
    serve_recorded(monkeypatch, served)
    by_name = {d.url_segment: d for d in served}

    def _fetch_at(_site: str, _record_type: str, search_name: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return format_param_info_typed(by_name[search_name].parameters or [])

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=ranked))


async def _answer(state: AgentToolState, call: ToolCallPart) -> object:
    args = call.args_as_dict()
    match call.tool_name:
        case "list_searches":
            state.record_catalog_read(listing([s.url_segment for s in _LISTED]))
            return [{"name": s.url_segment} for s in _LISTED]
        case "search_for_searches":
            ranked = await search_for_searches(
                agent_run_context(agent_state=state, tool_call_id=call.tool_call_id),
                query=args["query"],
            )
            return ranked.return_value
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


@dataclass
class _Pass:
    """What one FRAME pass sent to ``set_criterion`` and what it was refused."""

    bound: list[dict[str, Any]] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)


async def _played(state: AgentToolState) -> _Pass:
    """The FRAME pass on the other-site arc, until it sets the structure."""
    script = role_script("frame")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content="Frame work order")]
    played = _Pass()
    for _ in range(12):
        ctx = frame_ctx(state)
        pinned = "\n\n".join(
            b for b in (pinned_frame_sheets(ctx), pinned_frame_workspace(ctx)) if b
        )
        messages.append(ModelRequest(parts=parts, instructions=pinned))
        call = script(seen_by_the_model(messages))
        if call.tool_name in {"final_result", "set_structure"}:
            break
        if call.tool_name == "set_criterion" and "params" in call.args_as_dict():
            played.bound.append(call.args_as_dict()["params"])
        messages.append(ModelResponse(parts=[call]))
        try:
            reply: ToolReturnPart | RetryPromptPart = ToolReturnPart(
                tool_name=call.tool_name,
                content=await _answer(state, call),
                tool_call_id=call.tool_call_id,
            )
        except ModelRetry as refused:
            played.refusals.append(refused.message)
            reply = RetryPromptPart(
                content=refused.message,
                tool_name=call.tool_name,
                tool_call_id=call.tool_call_id,
            )
        parts = [reply]
    return played


async def _bound_on(
    monkeypatch: pytest.MonkeyPatch,
    definition: WDKSearch,
    site_id: str,
    ranked: list[SearchMatch] | None = None,
) -> tuple[_Pass, AgentToolState]:
    _serve(monkeypatch, definition, ranked)
    bind_scripted_scope(site_id, f"{_WORDS} [[arc:other-site-experiment]]")
    state = AgentToolState()
    return await _played(state), state


async def test_the_own_nearest_hit_binds_with_its_rank_as_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    played, state = await _bound_on(monkeypatch, _SIGNAL, "plasmodb")

    (criterion,) = state.operational_spec_draft.criteria
    assert played.refusals == []
    assert criterion.search_name == _SIGNAL.url_segment
    assert criterion.rationale is not None
    assert (criterion.rationale.basis, criterion.rationale.term) == ("nearest", _TERM)


async def test_of_two_hits_tied_at_two_decimals_the_one_the_tool_ranks_higher_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model reads both scores as 0.47; the tool compares the unrounded ones."""
    lower = match(
        _SIGNAL.url_segment, _SIGNAL.display_name, _SIGNAL.description, 0.4698
    )
    higher = match(
        _PERCENTILE.url_segment,
        _PERCENTILE.display_name,
        _PERCENTILE.description,
        0.4712,
    )

    played, state = await _bound_on(
        monkeypatch, _PERCENTILE, "plasmodb", ranked=[lower, higher]
    )

    (criterion,) = state.operational_spec_draft.criteria
    assert criterion.search_name == _PERCENTILE.url_segment
    assert criterion.rationale is not None
    assert criterion.rationale.basis == "nearest"
    assert [r.split(" scored higher than ")[0] for r in played.refusals] == [
        f"own_experiment: {_PERCENTILE.display_name}"
    ]


async def test_a_percentile_hit_sends_only_the_parameters_its_sheet_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    played, state = await _bound_on(monkeypatch, _PERCENTILE, "plasmodb")

    visible = {p.name for p in _PERCENTILE.parameters or [] if p.is_visible}
    (criterion,) = state.operational_spec_draft.criteria
    assert played.refusals == []
    assert [sorted(set(params) - visible) for params in played.bound] == [
        [] for _ in played.bound
    ]
    assert played.bound[-1]["samples_percentile_generic"] == ["asexual blood stages"]
    assert criterion.search_name == _PERCENTILE.url_segment


@pytest.mark.parametrize(
    ("definition", "reference", "comparison"),
    [
        (
            _SENSE_ANTISENSE,
            ("samples_ref_antisense", "Sugar_fed"),
            ("samples_comp_antisense", "Blood_fed"),
        ),
        (
            _FOLD_CHANGE,
            ("samples_fc_ref_generic", "Non-blood-fed"),
            ("samples_fc_comp_generic", "blood-fed 3h"),
        ),
    ],
)
async def test_a_contrast_hit_compares_two_different_sample_groups(
    monkeypatch: pytest.MonkeyPatch,
    definition: WDKSearch,
    reference: tuple[str, str],
    comparison: tuple[str, str],
) -> None:
    """Each side takes a group of its own sheet, the first two in the recorded order."""
    played, _state = await _bound_on(monkeypatch, definition, "vectorbase")

    sent = played.bound[-1]
    assert played.refusals == []
    assert (sent[reference[0]], sent[comparison[0]]) == (
        [reference[1]],
        [comparison[1]],
    )
