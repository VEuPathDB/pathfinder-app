"""A parameter the site sets is never asked for: a caller states only the
bindable ones, and a dependent vocabulary waits only for its stated parents."""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, to_wire
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParentContextRequired,
    ResolveContext,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import catalog_discovery
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    read_call,
)
from strategist.ai.tools.standalone._frame_result import SetCriterionResult
from strategist.ai.tools.standalone._variant_targets import resolved_variants
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.domain.strategy.session import StrategySession
from strategist.domain.strategy.site_set_reads import SiteSetReads
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import VariantInput
from strategist.services.parameter_optimization.tunable import (
    tunable_parameter_names,
)
from strategist.tests._support.catalog_reads import listing
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.record_classes import (
    list_searches_under,
    serve_record_classes,
)
from strategist.tests._support.recorded_searches import (
    client_search,
    serve_stated_reads,
    suite_search,
)
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools._rationale_catalog import choice
from strategist.tests.unit.ai.tools.conftest import (
    agent_run_context,
    patch_search_details,
)
from strategist.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    param_info,
    serve_search,
)

_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_PROFILESET = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)
_GIARDIA_TEXT = suite_search("search_giardiadb_genes_by_text")
_TEXT = suite_search("search_genes_by_text")
_SNPS = client_search("search_genes_by_ngs_snps")
_SNPS_UNDER_VIVAX = client_search("search_genes_by_ngs_snps_under_another_organism")
_VIVAX = "Plasmodium vivax P01"


async def test_a_dependent_read_under_its_stated_parent_names_no_site_set_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_search_details(monkeypatch, parameters=list(_PERCENTILE.parameters or []))

    result = returned(
        await catalog_discovery.get_parameter_options(
            agent_run_context(),
            search_name=_PERCENTILE.url_segment,
            parameter_id="samples_percentile_generic",
            context_values={"profileset_generic": _PROFILESET},
        ),
        ParameterInfo,
    )

    assert (bool(result.vocabulary()), "channel" in result.model_dump_json()) == (
        True,
        False,
    )


async def test_a_dependent_read_without_its_parent_names_only_the_stated_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_search_details(monkeypatch, parameters=list(_PERCENTILE.parameters or []))

    result = returned(
        await catalog_discovery.get_parameter_options(
            agent_run_context(),
            search_name=_PERCENTILE.url_segment,
            parameter_id="samples_percentile_generic",
        ),
        ParentContextRequired,
    )

    assert result.parent_parameter_ids == ["profileset_generic"]


async def test_a_vocabulary_under_only_a_site_set_parent_reads_with_no_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_search_details(monkeypatch, parameters=list(_GIARDIA_TEXT.parameters or []))

    result = returned(
        await catalog_discovery.get_parameter_options(
            agent_run_context(),
            search_name=_GIARDIA_TEXT.url_segment,
            parameter_id="text_fields",
        ),
        ParameterInfo,
    )

    assert "product" in {option.value for option in result.vocabulary()}


async def test_a_vocabulary_under_only_a_site_set_parent_is_checked_at_once() -> None:
    contexts: list[dict[str, str]] = []

    async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
        contexts.append(dict(context))
        return list(_GIARDIA_TEXT.parameters or [])

    call = CriterionCall(
        criterion_id="c1",
        search_name=_GIARDIA_TEXT.url_segment,
        text="genes annotated as cysteine-rich",
        params={"text_fields": ["no such field"]},
    )

    with pytest.raises(ModelRetry) as refused:
        await read_call(
            SearchContext("giardiadb", "transcript", _GIARDIA_TEXT.url_segment),
            fetch_at,
            call,
            definition=_GIARDIA_TEXT,
            state=AgentToolState(),
            about=ResolveContext(site_id="giardiadb"),
        )

    assert str(refused.value).startswith(
        "text_fields has no entry 'no such field'. Candidates: "
    )
    assert str(refused.value).endswith(" Nothing was recorded.")
    assert contexts == [{}, {"document_type": "gene"}]


def _read_only_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info("q"),
        param_info("ro", is_read_only=True, site_set=True, default_value="fixed"),
    ]


async def _bind_read_only(
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, JsonValue],
    state: AgentToolState | None = None,
) -> SetCriterionResult:
    serve_search(monkeypatch, _read_only_sheet)
    state = state or AgentToolState()
    state.record_catalog_read(listing(["GenesByReadOnly"]))
    state.request_messages = ["genes matching x"]
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="c1",
            text="genes matching x",
            search_name="GenesByReadOnly",
            params=params,
            why=choice("parameter", "q", "the request states x"),
        ),
        SetCriterionResult,
    )


async def test_a_read_only_parameter_needs_no_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()

    result = await _bind_read_only(monkeypatch, {"q": "x"}, state)

    assert (
        result.resolved_params["q"],
        result.corrections,
        SiteSetReads.of(state.infos_read_this_pass).by_search,
    ) == ("x", [], {"GenesByReadOnly": frozenset({"ro"})})


async def test_a_proposal_of_a_read_only_parameter_is_left_out_at_any_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()

    result = await _bind_read_only(monkeypatch, {"q": "x", "ro": "anything"}, state)

    [criterion] = state.operational_spec_draft.criteria
    assert (
        result.resolved_params["q"],
        result.corrections,
        to_wire(criterion.resolved_params["ro"].value),
    ) == ("x", ["ro is set by the site, so the proposal was left out"], "fixed")


async def _ngs_snps_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, search_name
    read = (
        _SNPS_UNDER_VIVAX if _VIVAX in context.get("organismSinglePick", "") else _SNPS
    )
    return sheet_of(list(read.parameters or []))


async def test_a_variant_sends_the_site_set_value_its_organism_gives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(variant_comparison, "search_parameters", _ngs_snps_parameters)
    serve_stated_reads(monkeypatch, [_SNPS])
    serve_record_classes(monkeypatch)
    list_searches_under(monkeypatch, "transcript", ["GenesByNgsSnps"])
    variant = VariantInput.model_validate(
        {
            "label": "vivax SNPs",
            "searchName": "GenesByNgsSnps",
            "parameters": {"organismSinglePick": [_VIVAX]},
        }
    )

    (spec,) = await resolved_variants(
        StrategySession(site_id="plasmodb"),
        [variant],
        ResolveContext(site_id="plasmodb"),
    )

    assert (
        spec.parameters["organismSinglePick"],
        spec.parameters["eda_sample_table_suffix"],
    ) == (
        MultiPickValue(values=[_VIVAX]),
        SinglePickValue(value="sba1cd4a562_sample"),
    )


def _tunable(search: WDKSearch) -> list[str]:
    return tunable_parameter_names(sheet_of(list(search.parameters or [])))


def test_a_vocabulary_under_only_a_site_set_parent_is_tunable() -> None:
    assert "text_fields" in _tunable(_TEXT)


def test_a_parameter_a_site_set_value_follows_is_not_tunable() -> None:
    assert "organismSinglePick" not in _tunable(_SNPS)
