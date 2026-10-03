"""A pick names the options it did not take only when another option counts
differently; an option whose count the site refuses is no reading and makes no
caveat, and a default multi-pick is counted at every option."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
    VocabOption,
)
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.domain.value_caveats import (
    ChoiceCaveat,
    assumed_value_caveats,
)
from pathfinder.services.strategies.measurements import (
    MeasuredBinding,
    TurnCounts,
    measure_binding,
)
from pathfinder.services.strategies.pick_readings import default_reading
from pathfinder.tests._support.recorded_counts import (
    PERCENTILE_SEARCH,
    percentile_count,
    recorded_count,
    serve_counts,
    wire,
)
from pathfinder.tests._support.recorded_searches import suite_search

_LIFE_STAGES = (
    "GenesByMicroarrayDirectWithConfidencelmajFriedlin_microarrayExpression_"
    "E-MEXP-1864_Beverley_Steve_LifeStages_RSRC"
)
_PNA = "pnaVsPromastigote"
_AMA = "amastigoteVsPromastigote"
_SENSE = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)
_PF3D7 = "Plasmodium falciparum 3D7"


def _life_stages() -> list[ParameterInfo]:
    """The tritrypdb Experiment as WDK publishes it: hidden, two comparisons."""
    return [
        ParameterInfo(
            name="profileset_generic",
            display_name="Experiment",
            type="single-pick-vocabulary",
            required=True,
            is_visible=False,
            help="",
            value_format="",
            default_value=_PNA,
            allowed_values=[VocabOption(value=v, display=v) for v in (_PNA, _AMA)],
        )
    ]


def _criterion(
    name: str,
    display: str,
    value: ParamValue,
    measured: list[Measurement],
    count: int,
) -> Criterion:
    return Criterion(
        id="c_1",
        text="the step",
        search_name="S",
        resolved_params={name: BoundValue(value=value, source="default")},
        param_display_names={name: display},
        measurements=measured,
        result_count=count,
    )


@pytest.mark.asyncio
async def test_a_default_comparison_whose_other_option_counts_fewer_is_a_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
        assert wire(params, "profileset_generic") == _AMA
        return recorded_count("report_life_stages_amastigote")

    asked = serve_counts(monkeypatch, _count)
    value = SinglePickValue(value=_PNA)
    bound = recorded_count("report_life_stages_pna")

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="tritrypdb",
            record_type="transcript",
            search_name=_LIFE_STAGES,
            params={"profileset_generic": value},
            count=bound,
        ),
        values=bind_values({"profileset_generic": value}, "default", _life_stages()),
        infos=_life_stages(),
    )

    assert (bound, asked, measured) == (
        142,
        [_LIFE_STAGES],
        [
            Measurement(
                kind="options_not_taken",
                param="profileset_generic",
                unchosen=[_AMA],
                unchosen_count=1,
            )
        ],
    )
    (caveat,) = assumed_value_caveats(
        OperationalSpec(
            criteria=[
                _criterion("profileset_generic", "Experiment", value, measured, bound)
            ]
        )
    )
    assert caveat == ChoiceCaveat(
        criterion_id="c_1",
        param_display_name="Experiment",
        value=_PNA,
        source="default",
        unchosen=[_AMA],
        unchosen_count=1,
    )


@pytest.mark.asyncio
async def test_a_percentile_step_names_only_the_picks_that_change_its_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, percentile_count)
    params: dict[str, ParamValue] = {
        "profileset_generic": SinglePickValue(value=_SENSE),
        "samples_percentile_generic": MultiPickValue(values=["asexual blood stages"]),
        "min_expression_percentile": StringValue(value="80"),
        "max_expression_percentile": StringValue(value="100"),
        "any_or_all": SinglePickValue(value="any"),
        "protein_coding_only": SinglePickValue(value="yes"),
        "channel": SinglePickValue(value="Channel 1"),
    }
    picks = ("profileset_generic", "any_or_all", "protein_coding_only", "channel")
    infos = format_param_info_typed(
        list(
            suite_search("search_genes_by_rnaseq_gomez_diaz_percentile").parameters
            or []
        )
    )
    values = bind_values({n: params[n] for n in picks}, "default", infos)
    bound = recorded_count("report_percentile_min_80")

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name=PERCENTILE_SEARCH,
            params=params,
            count=bound,
        ),
        values=values,
        infos=infos,
    )

    assert (bound, measured) == (
        1087,
        [
            Measurement(
                kind="options_not_taken",
                param="profileset_generic",
                unchosen=[
                    (
                        "Asexual blood stages, salivary gland sporozoite and midgut "
                        "oocyst transcriptomes - Antisense"
                    )
                ],
                unchosen_count=1,
            ),
            Measurement(
                kind="options_not_taken",
                param="protein_coding_only",
                unchosen=["all"],
                unchosen_count=1,
            ),
        ],
    )
    criterion = Criterion(
        id="c_1",
        text="the step",
        search_name=PERCENTILE_SEARCH,
        resolved_params=values,
        param_display_names={i.name: i.display_name for i in infos},
        measurements=measured,
        result_count=bound,
    )
    assert [
        (c.kind, c.param_display_name)
        for c in assumed_value_caveats(OperationalSpec(criteria=[criterion]))
    ] == [("chosen_among", "Experiment"), ("chosen_among", "Protein Coding Only:")]


def _gene_types() -> list[ParameterInfo]:
    return format_param_info_typed(
        list(suite_search("search_genes_by_gene_type").parameters or [])
    )


def _snps() -> list[ParameterInfo]:
    return format_param_info_typed(
        list(suite_search("search_genes_by_ngs_snps").parameters or [])
    )


def _gene_type_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    assert json.loads(wire(params, "geneType")) == [
        "misc RNA",
        "protein coding",
        "pseudogene",
    ]
    return recorded_count("report_gene_type_every_type")


@pytest.mark.asyncio
async def test_a_default_multi_pick_subset_is_counted_at_every_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, _gene_type_count)
    value = MultiPickValue(values=["protein coding"])
    bound = recorded_count("report_gene_type_protein_coding")

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByGeneType",
            params={
                "organism": MultiPickValue(values=[_PF3D7]),
                "geneType": value,
                "includePseudogenes": SinglePickValue(value="No"),
            },
            count=bound,
        ),
        values=bind_values({"geneType": value}, "default", _gene_types()),
        infos=_gene_types(),
    )

    assert (bound, measured) == (
        5318,
        [
            Measurement(
                kind="loosest_bound",
                param="geneType",
                count=5562,
                reading="all 3 options",
            ),
            Measurement(
                kind="options_not_taken",
                param="geneType",
                unchosen=["misc RNA", "pseudogene"],
                unchosen_count=2,
            ),
        ],
    )
    assert [
        c.sentence
        for c in assumed_value_caveats(
            OperationalSpec(
                criteria=[_criterion("geneType", "Gene type", value, measured, bound)]
            )
        )
        if c.kind == "assumed_value"
    ] == [
        (
            "Gene type is protein coding, the site's default: 5,318 genes at that "
            "value, 5,562 at all 3 options"
        )
    ]


@pytest.mark.asyncio
async def test_a_multi_pick_whose_other_reading_the_site_refuses_is_no_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_counts(monkeypatch, lambda _s, _p: None)
    value = MultiPickValue(values=["protein coding"])

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByGeneType",
            params={
                "organism": MultiPickValue(values=[_PF3D7]),
                "geneType": value,
                "includePseudogenes": SinglePickValue(value="No"),
            },
            count=recorded_count("report_gene_type_protein_coding"),
        ),
        values=bind_values({"geneType": value}, "default", _gene_types()),
        infos=_gene_types(),
    )

    assert measured == []


@pytest.mark.asyncio
async def test_a_tree_pick_records_that_options_not_taken_do_not_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = serve_counts(monkeypatch, lambda _s, _p: None)
    value = MultiPickValue(values=[_PF3D7])

    measured = await measure_binding(
        TurnCounts(),
        MeasuredBinding(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByNgsSnps",
            params={"organismSinglePick": value},
            count=None,
        ),
        values=bind_values({"organismSinglePick": value}, "default", _snps()),
        infos=_snps(),
    )

    assert (asked, measured) == (
        [],
        [
            Measurement(
                kind="bound_count",
                param="organismSinglePick",
                reading=f'["{_PF3D7}"]',
            ),
            Measurement(
                kind="not_measurable",
                param="organismSinglePick",
                reading=(
                    "options not taken: not applicable, since a parent term takes "
                    "the options under it"
                ),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_every_option_of_a_large_vocabulary_is_named_with_its_separator() -> None:
    info = ParameterInfo(
        name="domain_typeahead",
        display_name="Specific Domain(s)",
        type="multi-pick-vocabulary",
        required=True,
        is_visible=True,
        help="",
        value_format="",
        allowed_values=[
            VocabOption(value=f"PF{n:05d}", display=f"PF{n:05d}")
            for n in range(1, 2442)
        ],
    )

    async def _count(_params: Mapping[str, ParamValue]) -> int:
        return 4444

    [held] = bind_values(
        {info.name: MultiPickValue(values=["PF00001"])}, "default", [info]
    ).values()

    measured = await default_reading(_count, info.name, held, info, 37)

    assert [(m.kind, m.count, m.reading) for m in measured[:1]] == [
        ("loosest_bound", 4444, "all 2,441 options")
    ]
