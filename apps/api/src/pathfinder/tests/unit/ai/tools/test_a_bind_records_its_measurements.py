"""A bound criterion records its parameters' display names, the label of each
pick and the counts of the other readings of each value the site set, and the
tool names each measurement in one clause."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import FilterValue, SinglePickValue
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count, frame_spec
from pathfinder.ai.tools.standalone._frame_measure import labelled_picks
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
)
from pathfinder.domain.value_caveats import assumed_value_caveats
from pathfinder.tests._support.recorded_counts import (
    PERCENTILE_SEARCH,
    percentile_count,
    recorded_count,
    serve_counts,
)
from pathfinder.tests._support.recorded_searches import serve_recorded, suite_search
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_REQUEST = "genes expressed in asexual blood stages"
_PARAMS: dict[str, str | list[str] | None] = {
    "profileset_generic": None,
    "samples_percentile_generic": ["asexual blood stages"],
    "min_expression_percentile": None,
    "max_expression_percentile": None,
    "any_or_all": None,
    "protein_coding_only": None,
}


def _sheet() -> list[ParameterInfo]:
    return format_param_info_typed(list(_PERCENTILE.parameters or []))


def _serve(
    monkeypatch: pytest.MonkeyPatch, bound_count: int | None, *, measured: bool = True
) -> list[str]:
    serve_recorded(monkeypatch, [_PERCENTILE])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return _sheet()

        return fetch_at

    async def _count(*_args: object, **_kwargs: object) -> int | None:
        return bound_count

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)
    no_validation(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)

    return serve_counts(
        monkeypatch, percentile_count if measured else lambda _s, _p: None
    )


async def _bound(state: AgentToolState) -> tuple[Criterion, list[str]]:
    state.request_messages = [_REQUEST]
    result = await bind(state, PERCENTILE_SEARCH, dict(_PARAMS), text=_REQUEST)
    [criterion] = state.operational_spec_draft.criteria
    return criterion, result.measurements


@pytest.mark.asyncio
async def test_a_default_percentile_is_recorded_with_its_loosest_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, recorded_count("report_percentile_min_80"))

    criterion, clauses = await _bound(AgentToolState())

    assert criterion.resolved_params["min_expression_percentile"].source == "default"
    assert [m for m in criterion.measurements if m.kind == "loosest_bound"] == [
        Measurement(
            kind="loosest_bound",
            param="min_expression_percentile",
            count=5318,
            reading="0",
        )
    ]
    assert (
        "Minimum expression percentile at the site's default of 80: 1,087 genes; "
        "at 0: 5,318"
    ) in clauses


@pytest.mark.asyncio
async def test_the_caveat_names_the_parameter_by_its_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, recorded_count("report_percentile_min_80"))
    state = AgentToolState()

    await _bound(state)

    caveats = assumed_value_caveats(state.operational_spec_draft)
    assert [c.sentence for c in caveats if c.kind == "assumed_value"] == [
        (
            "Minimum expression percentile is 80, the site's default: 1,087 genes "
            "at that value, 5,318 at 0"
        )
    ]
    assert [c.sentence for c in caveats if c.kind == "chosen_among"] == [
        (
            "Experiment is Asexual blood stages and salivary gland sporozoite and "
            "midgut oocyst transcriptomes - Sense, the site's default; the options "
            "not taken: Asexual blood stages, salivary gland sporozoite and midgut "
            "oocyst transcriptomes - Antisense"
        ),
        "Protein Coding Only: is yes, the site's default; the options not taken: all",
    ]
    assert [c.sentence for c in caveats if c.kind == "unmeasured_value"] == []


@pytest.mark.asyncio
async def test_a_number_whose_reading_did_not_arrive_is_a_caveat_and_a_pick_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, recorded_count("report_percentile_min_80"), measured=False)
    state = AgentToolState()

    _, clauses = await _bound(state)

    caveats = assumed_value_caveats(state.operational_spec_draft)
    assert [c.sentence for c in caveats if c.kind == "unmeasured_value"] == [
        (
            "Minimum expression percentile is 80, the site's default: its effect "
            "was not measured, since the count at 0 did not arrive"
        ),
        (
            "Maximum expression percentile is 100, the site's default: its effect "
            "was not measured, since the count at 0 did not arrive"
        ),
    ]
    assert (
        "Minimum expression percentile at the site's default of 80: 1,087 genes; "
        "at 0: not measured"
    ) in clauses


@pytest.mark.asyncio
async def test_every_pick_is_recorded_with_its_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, recorded_count("report_percentile_min_80"))

    criterion, clauses = await _bound(AgentToolState())

    labels = {m.param: m.label for m in criterion.measurements if m.label}
    assert labels["protein_coding_only"] == "protein coding"
    assert criterion.param_display_names["samples_percentile_generic"] == "Samples"
    assert "Protein Coding Only: yes is labelled 'protein coding'" in clauses


@pytest.mark.asyncio
async def test_a_binding_that_counted_nothing_reads_no_other_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve(monkeypatch, None)
    state = AgentToolState()

    criterion, _ = await _bound(state)

    assert asked == []
    assert [m.param for m in criterion.measurements if m.kind == "bound_count"] == [
        "profileset_generic",
        "min_expression_percentile",
        "max_expression_percentile",
        "any_or_all",
        "protein_coding_only",
        "channel",
    ]


@pytest.mark.asyncio
async def test_a_default_on_a_binding_that_counted_nothing_was_not_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, None)
    state = AgentToolState()

    await _bound(state)

    caveats = assumed_value_caveats(state.operational_spec_draft)
    assert [c.sentence for c in caveats if c.kind == "unmeasured_value"][1:3] == [
        (
            "Minimum expression percentile is 80, the site's default: its effect "
            "was not measured, since the count of the search at 80 did not arrive"
        ),
        (
            "Maximum expression percentile is 100, the site's default: its effect "
            "was not measured, since the count of the search at 100 did not arrive"
        ),
    ]


@pytest.mark.asyncio
async def test_a_second_bind_of_the_same_values_reads_the_turns_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A count that arrived is read once a turn; one the site failed to answer
    is asked again."""
    asked = _serve(monkeypatch, recorded_count("report_percentile_min_80"))
    state = AgentToolState()

    await _bound(state)
    first = len(asked)
    await _bound(state)

    assert (first, len(asked)) == (6, 7)


def _maybe() -> dict[str, BoundValue]:
    return {
        "protein_coding_only": BoundValue(
            value=SinglePickValue(value="maybe"), source="chosen"
        )
    }


async def _fetch_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return _sheet()


def _call(proposed: str | None) -> CriterionCall:
    return CriterionCall(
        criterion_id="c1",
        search_name=PERCENTILE_SEARCH,
        text=_REQUEST,
        params={"protein_coding_only": proposed},
    )


@pytest.mark.asyncio
async def test_a_proposed_pick_its_vocabulary_does_not_label_is_refused() -> None:
    with pytest.raises(ModelRetry, match=r"\['protein coding', 'all'\]"):
        await labelled_picks(_fetch_sheet, _sheet(), _call("maybe"), _maybe())


@pytest.mark.asyncio
async def test_a_value_the_site_supplied_without_a_label_is_recorded_unlabelled() -> (
    None
):
    labels = await labelled_picks(_fetch_sheet, _sheet(), _call(None), _maybe())

    assert labels == []


_SNPS = suite_search("search_genes_by_ngs_snps")
_SAMPLES = "variation_sample_meta"


def _snps_sheet() -> list[ParameterInfo]:
    return format_param_info_typed(list(_SNPS.parameters or []))


async def _fetch_snps(_context: dict[str, str]) -> list[ParameterInfo]:
    return _snps_sheet()


@pytest.mark.asyncio
async def test_a_filter_clause_on_a_field_the_sheet_lacks_is_refused_by_its_labels() -> (
    None
):
    proposal = '{"filters": [{"field": "VAR_00000000", "value": ["female"]}]}'
    bound = {
        _SAMPLES: BoundValue(
            value=FilterValue.model_validate(
                {"filters": [{"field": "VAR_00000000", "value": ["female"]}]}
            ),
            source="chosen",
        )
    }
    call = CriterionCall(
        criterion_id="c1",
        search_name=_SNPS.url_segment,
        text="SNPs in female samples",
        params={_SAMPLES: proposal},
    )

    with pytest.raises(ModelRetry) as refused:
        await labelled_picks(_fetch_snps, _snps_sheet(), call, bound)

    assert "'sex'" in str(refused.value)
    assert "VAR_00000000" in str(refused.value)
