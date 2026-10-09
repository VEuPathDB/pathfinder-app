"""A bind the tool can correct is corrected and recorded; a bind it cannot
correct is refused with the exact names or words to use.

Each call replays the arguments a refused bind carried, on the recorded sheet
of a search with the same parameters.
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import to_wire
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.recorded_counts import no_measurements
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_plasmodb,
    suite_search,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    EXPORTED,
    SIGNAL,
    choice,
    read,
    refused,
    serve_site,
)
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    param_info,
    serve_search,
    serve_site_listing,
)

_TEXT = suite_search("search_genes_by_text")
_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_ORGANISM = "Plasmodium falciparum 3D7"
_PROFILESET = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)
Proposals = dict[str, str | list[str] | None]


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_plasmodb(monkeypatch, [_TEXT, _PERCENTILE])
    no_validation(monkeypatch)
    no_measurements(monkeypatch)
    serve_no_other_sites(monkeypatch)


async def _bind(
    state: AgentToolState,
    search: WDKSearch,
    params: Proposals,
    why: dict[str, str],
    *,
    criterion_id: str = "c1",
    text: str,
) -> SetCriterionResult:
    state.record_catalog_read(listing([search.url_segment]))
    state.request_messages = state.request_messages or [text]
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id=criterion_id,
            text=text,
            search_name=search.url_segment,
            params=params,
            why=choice(**why),
        ),
        SetCriterionResult,
    )


_TACHYZOITE: Proposals = {
    "channel": "Channel 1",
    "any_or_all": "any",
    "profileset_generic": _PROFILESET,
    "protein_coding_only": "yes",
    "max_expression_percentile": "100",
    "min_expression_percentile": "50",
    "samples_percentile_generic": ["asexual blood stages"],
}
_PERCENTILE_WHY = {
    "term": "Minimum Expression Percentile",
    "basis": "parameter",
    "reason": "The requested cutoff changes from the 80th to the 50th percentile.",
}


@pytest.mark.asyncio
async def test_a_hidden_choice_at_the_sites_value_binds_as_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    result = await _bind(
        state,
        _PERCENTILE,
        dict(_TACHYZOITE),
        _PERCENTILE_WHY,
        text="genes expressed in asexual blood stages at or above the 50th percentile",
    )

    [criterion] = state.operational_spec_draft.criteria
    channel = criterion.resolved_params["channel"]
    assert (result.corrections, to_wire(channel.value), channel.source) == (
        [],
        "Channel 1",
        "default",
    )


@pytest.mark.asyncio
async def test_a_hidden_choice_at_another_of_its_values_binds_as_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    await _bind(
        state,
        _PERCENTILE,
        _TACHYZOITE | {"channel": "Channel 2"},
        _PERCENTILE_WHY,
        text="genes expressed in asexual blood stages at the 50th percentile",
    )

    [criterion] = state.operational_spec_draft.criteria
    channel = criterion.resolved_params["channel"]
    assert (to_wire(channel.value), channel.source) == ("Channel 2", "chosen")


_VES: Proposals = {
    "text_fields": ["product"],
    "document_type": "gene",
    "text_expression": "*ves*",
    "text_search_organism": [_ORGANISM],
}


@pytest.mark.asyncio
async def test_the_document_type_a_text_bind_copies_is_left_to_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    result = await _bind(
        state,
        _TEXT,
        dict(_VES),
        {
            "term": "Text term (use * as wildcard)",
            "basis": "parameter",
            "reason": "A wildcard text search captures product annotations.",
        },
        text="genes annotated in the ves multigene family",
    )

    assert result.corrections == [
        "document_type is set by the site to 'gene', so the proposal was left out"
    ]
    assert result.rationale is not None
    assert result.rationale.term == "Text term (use * as wildcard)"


@pytest.mark.asyncio
async def test_a_value_only_the_site_sets_is_refused_at_another_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refusal:
        await _bind(
            state,
            _TEXT,
            _VES | {"document_type": "transcript"},
            {
                "term": "Text term (use * as wildcard)",
                "basis": "parameter",
                "reason": "A wildcard text search captures product annotations.",
            },
            text="genes annotated in the ves multigene family",
        )

    assert str(refusal.value) == (
        f"document_type on {_TEXT.url_segment} is set by the site to 'gene' and "
        f"takes no other value; leave it out of params. The names params takes: "
        f"['text_expression', 'text_fields', 'text_search_organism']."
    )
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_a_display_name_without_its_parenthetical_names_the_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    result = await _bind(
        state,
        _TEXT,
        {
            "text_fields": ["product"],
            "text_expression": "ves",
            "text_search_organism": [_ORGANISM],
        },
        {
            "term": "Text term",
            "basis": "parameter",
            "reason": "The text search matches the ves annotation in product text.",
        },
        text="genes annotated in the ves multigene family",
    )

    assert result.rationale is not None
    assert result.rationale.term == "Text term (use * as wildcard)"
    assert result.corrections == [
        (
            "why.term corrected to Text term (use * as wildcard): Text term names "
            "the parameter text_expression"
        )
    ]


def _fold_change_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info("fold_change", display_name="Fold change", default_value="2"),
        param_info(
            "dataset_url",
            is_visible=False,
            required=False,
            default_value="https://qa.tritrypdb.org/a/app/record/dataset/DS_3e90742f0a",
        ),
    ]


@pytest.mark.asyncio
async def test_the_dataset_url_a_step_carries_is_left_to_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _fold_change_sheet)
    serve_site_listing(monkeypatch, [])
    state = AgentToolState()
    search = WDKSearch.model_validate(
        {"url_segment": "GenesByRNASeqFoldChange", "display_name": "Fold change"}
    )

    result = await _bind(
        state,
        search,
        {
            "fold_change": "4",
            "dataset_url": (
                "https://qa.tritrypdb.org/a/app/record/dataset/DS_3e90742f0a"
            ),
        },
        {"term": "fold_change", "basis": "parameter", "reason": "raised to 4-fold"},
        text="genes up 4-fold",
    )

    assert result.corrections == [
        (
            "dataset_url is set by the site to "
            "'https://qa.tritrypdb.org/a/app/record/dataset/DS_3e90742f0a', so the "
            "proposal was left out"
        )
    ]
    assert result.resolved_params["fold_change"] == "4"


@pytest.mark.asyncio
async def test_a_phrase_the_search_does_not_hold_is_refused_with_its_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_site(monkeypatch)
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    message = await refused(
        state,
        choice("only_match", "predicted to be secreted", "the direct search"),
    )

    assert message == (
        "c_gpi: the name and the description of GenesByExportPrediction do not "
        "hold predicted to be secreted. They read: Exported Protein; Find genes "
        "that are predicted by ExportPred to produce an exported protein. Pass as "
        "the term a phrase of the request these words hold, or give another basis."
    )


_HELD_WHY = SearchRationale(
    search_name=_PERCENTILE.url_segment,
    basis="parameter",
    term="Samples",
    reason="the asexual blood stage sample",
    tool_call_id="call_turn1_read",
)


@pytest.mark.asyncio
async def test_a_value_edit_with_a_why_needs_no_catalog_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    held = Criterion(
        id="step_a9d79b5d",
        text="genes expressed in asexual blood stages",
        search_name=_PERCENTILE.url_segment,
        rationale=_HELD_WHY,
    )
    state = AgentToolState(operational_spec_draft=OperationalSpec(criteria=[held]))
    state.request_messages = ["genes expressed in asexual blood stages, top 5 percent"]
    params = {k: v for k, v in _TACHYZOITE.items() if k != "channel"}

    result = returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="step_a9d79b5d",
            text="genes expressed in asexual blood stages at the top 5 percent",
            search_name=_PERCENTILE.url_segment,
            params=params | {"min_expression_percentile": "95"},
            why=choice(
                "parameter",
                "Minimum expression percentile",
                "Top 5% corresponds to percentile 95 through 100.",
            ),
        ),
        SetCriterionResult,
    )

    assert result.resolved_params["min_expression_percentile"] == "95"
    assert result.rationale is not None
    assert (result.rationale.reason, result.rationale.tool_call_id) == (
        "Top 5% corresponds to percentile 95 through 100.",
        "call_turn1_read",
    )
