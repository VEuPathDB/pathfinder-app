"""set_criterion binds a value on the scale its parameter names, and records a
value as stated when the researcher's words hold it: as an ordinal, on the
other scale, or by the label the site gives it."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import to_wire
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count, frame_spec
from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.tests._support.recorded_counts import percentile_count, serve_counts
from pathfinder.tests._support.recorded_searches import serve_recorded, suite_search
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_FOLD = suite_search("search_genes_by_microarray_aaeg_blood_meal_fold_change")
_TAXON = suite_search("search_genes_by_taxon_piroplasmadb")
_TIGHTEN = "tighten it to the 95th percentile and tell me how the final count changes?"
_LOG2_ASK = (
    "Aedes aegypti genes up-regulated at blood-fed 24h over non-blood-fed, "
    "log2 fold change of 1 or more"
)
_BABESIA = "Now try Babesia microti RI instead."


def _serve(monkeypatch: pytest.MonkeyPatch, search: WDKSearch) -> None:
    serve_recorded(monkeypatch, [search])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return format_param_info_typed(list(search.parameters or []))

        return fetch_at

    async def _count(*_args: object, **_kwargs: object) -> int | None:
        return None

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)
    no_validation(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)
    serve_counts(monkeypatch, percentile_count)


async def _bound(
    search: WDKSearch, params: dict[str, str | list[str] | None], said: str
) -> dict[str, BoundValue]:
    state = AgentToolState()
    state.request_messages = [said]
    await bind(state, search.url_segment, params, text=said)
    [criterion] = state.operational_spec_draft.criteria
    return criterion.resolved_params


@pytest.mark.asyncio
async def test_a_95th_percentile_the_researcher_wrote_is_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _PERCENTILE)

    bound = await _bound(
        _PERCENTILE,
        {
            "profileset_generic": None,
            "samples_percentile_generic": ["asexual blood stages"],
            "min_expression_percentile": "95",
            "max_expression_percentile": None,
            "any_or_all": None,
            "protein_coding_only": None,
        },
        _TIGHTEN,
    )

    held = bound["min_expression_percentile"]
    assert (to_wire(held.value), held.source, held.basis) == ("95", "stated", "95th")


@pytest.mark.asyncio
async def test_a_log2_number_binds_a_fold_parameter_at_its_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _FOLD)

    bound = await _bound(
        _FOLD,
        {
            "regulated_dir": "up-regulated",
            "samples_fc_ref_generic": ["Non-blood-fed"],
            "samples_fc_comp_generic": ["blood-fed 24h"],
            "fold_change": "1",
            "profileset_generic": None,
            "min_max_avg_ref": None,
            "min_max_avg_comp": None,
            "protein_coding_only": None,
        },
        _LOG2_ASK,
    )

    held = bound["fold_change"]
    assert (to_wire(held.value), held.source, held.basis) == (
        "2",
        "stated",
        "log2 fold change of 1",
    )


@pytest.mark.asyncio
async def test_an_organism_the_researcher_named_without_its_rank_word_is_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _TAXON)

    bound = await _bound(_TAXON, {"organism": ["Babesia microti strain RI"]}, _BABESIA)

    held = bound["organism"]
    assert (held.source, held.basis) == ("stated", "Babesia microti RI")
