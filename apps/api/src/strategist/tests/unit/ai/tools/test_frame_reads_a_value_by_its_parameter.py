"""FRAME reads each value the model states through its parameter's own rule."""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from pydantic_ai.tools import ToolDefinition
from veupathdb.domain.parameters import (
    FilterValue,
    NumberBounds,
    NumberRange,
)
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import FilterReads, ParamFetcher, format_param_info_typed

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import _frame_proposals, frame_spec
from strategist.ai.tools.standalone._frame_schema import name_the_open_sheets
from strategist.ai.tools.standalone._frame_sheet import open_parameter_sheet
from strategist.domain.strategy.card_answers import option_refusal
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.value_text import clause_text
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recorded_counts import no_measurements
from strategist.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from strategist.tests.unit.ai.tools.conftest import serve_no_other_sites
from strategist.tests.unit.ai.tools.test_frame_spec import (
    bind,
    frame_ctx,
    no_validation,
    serve_site_listing,
)

_SNPS = suite_search("search_genes_by_ngs_snps")
_VARIANTS = suite_search("search_genes_by_variant_characteristics")
_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_PF = "Plasmodium falciparum 3D7"


def _serve(monkeypatch: pytest.MonkeyPatch, definition: WDKSearch) -> None:
    list_every_search_under(monkeypatch, "transcript")
    serve_recorded(monkeypatch, [definition])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[WDKParameter]:
            return list(definition.parameters or [])

        return fetch_at

    def _reads(_site: str, _record_type: str, _search: str) -> FilterReads:
        return NoFilterReads()

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_proposals, "WDKFilterReads", _reads)
    no_validation(monkeypatch)
    no_count(monkeypatch)
    no_measurements(monkeypatch)
    serve_site_listing(monkeypatch, [])
    serve_no_other_sites(monkeypatch)


def _every_null(definition: WDKSearch) -> dict[str, JsonValue]:
    return {
        info.name: None
        for info in format_param_info_typed(definition.parameters or [])
        if info.bindable
    }


async def _bound(
    monkeypatch: pytest.MonkeyPatch,
    definition: WDKSearch,
    stated: dict[str, JsonValue],
    text: str = "kinases",
) -> AgentToolState:
    _serve(monkeypatch, definition)
    state = AgentToolState()
    await bind(
        state, definition.url_segment, _every_null(definition) | stated, text=text
    )
    return state


async def test_a_float_for_a_number_string_records_its_shortest_decimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _bound(
        monkeypatch,
        _SNPS,
        {"organismSinglePick": [_PF], "MinPercentMinorAlleles": 5.0},
        "SNPs whose minor alleles reach 5 percent",
    )

    [criterion] = state.operational_spec_draft.criteria
    held = criterion.resolved_params["MinPercentMinorAlleles"]
    assert (held.value.to_wire(), held.source) == ("5", "stated")


async def test_a_filter_written_as_text_is_refused_and_nothing_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await _bound(monkeypatch, _VARIANTS, {"gene_variant_stats": "total_variants>5"})

    assert refused.value.message.startswith("gene_variant_stats takes a list")
    assert refused.value.message.endswith("Nothing was recorded.")


async def test_a_filter_text_leaves_the_draft_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _VARIANTS)
    state = AgentToolState()

    with pytest.raises(ModelRetry):
        await bind(
            state,
            _VARIANTS.url_segment,
            _every_null(_VARIANTS) | {"gene_variant_stats": "total_variants>5"},
        )

    assert state.operational_spec_draft.criteria == []


async def test_a_filter_clause_object_records_a_number_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _bound(
        monkeypatch,
        _VARIANTS,
        {
            "organism_select_none": [_PF],
            "gene_variant_stats": [{"field": "total_variants", "value": {"min": 6}}],
        },
    )

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.resolved_params["gene_variant_stats"].value == FilterValue(
        filters=[
            NumberRange(
                field="total_variants",
                type="number",
                is_range=True,
                include_unknown=False,
                value=NumberBounds(min=6),
            )
        ]
    )


async def test_a_boolean_for_a_yes_no_vocabulary_names_its_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await _bound(monkeypatch, _PERCENTILE, {"protein_coding_only": True})

    assert "one of 'yes', 'no'" in refused.value.message


def _set_criterion_tool() -> ToolDefinition:
    return ToolDefinition(
        name="set_criterion",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "params": {
                    "anyOf": [
                        {"type": "object", "additionalProperties": True},
                        {"type": "null"},
                    ]
                }
            },
            "$defs": {
                "SearchChoice": {
                    "type": "object",
                    "properties": {
                        "basis": {"enum": ["parameter", "only_match"]},
                        "term": {"type": "string", "description": "The term."},
                    },
                }
            },
        },
    )


def test_an_open_sheet_states_each_parameters_schema() -> None:
    state = AgentToolState()
    open_parameter_sheet(state, "c_snps", _SNPS.url_segment, _SNPS)

    prepared = name_the_open_sheets(frame_ctx(state), _set_criterion_tool())

    params = prepared.parameters_json_schema["properties"]["params"]["anyOf"][0]
    assert params["properties"]["ReadFrequencyPercent"] == {
        "anyOf": [
            {"enum": ["80%", "60%", "40%", "20%"], "type": "string"},
            {"type": "null"},
        ]
    }


_HERMAPHRODITE = (
    '{"filters":[{"field":"VAR_68bb04bd","type":"string","isRange":false,'
    '"includeUnknown":false,"value":["hermaphrodite"]}]}'
)


def test_a_card_option_a_facet_lacks_is_refused_with_its_members() -> None:
    sheet = format_param_info_typed(_SNPS.parameters or [])
    spec = OperationalSpec(
        criteria=[
            Criterion(
                id="c_snps",
                text="SNPs in hermaphrodite samples",
                search_name=_SNPS.url_segment,
                open_params=[
                    OpenSlot(
                        criterion_id="c_snps",
                        param_name="variation_sample_meta",
                        param_kind="filter",
                    )
                ],
            )
        ]
    )

    refusal = option_refusal(
        spec,
        SetValues(
            criterion_id="c_snps", params={"variation_sample_meta": _HERMAPHRODITE}
        ),
        sheets={"c_snps": sheet},
        expressions={},
    )

    assert refusal is not None
    assert "its members are female, male" in refusal


def test_a_range_clause_reads_as_its_bound() -> None:
    clause = NumberRange(
        field="total_variants",
        type="number",
        is_range=True,
        include_unknown=False,
        value=NumberBounds(min=6),
    )

    assert clause_text(clause) == "total_variants: at least 6"
