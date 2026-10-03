"""The columns a step's search shows for its bound values, mapped from plasmodb's
recorded catalog by the WDK type of each parameter, and the records inside the
bounds, from recorded reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import TypeAdapter
from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.wdk import WDKParameter

from pathfinder.ai.tools.standalone._step_columns import (
    AttributeHistogram,
    Bounds,
    ColumnBound,
    Measured,
    Threshold,
    by_value_bins,
    column_bounds,
    measured,
    settled,
)
from pathfinder.domain.evidence import ColumnFit, ThresholdSides
from pathfinder.tests._support.recorded_columns import (
    PERCENTILE_SEARCH,
    attribute_histogram,
    by_value,
    catalog_search,
    column_catalog,
)

_PARAMETERS = TypeAdapter(list[WDKParameter])
# The value a number range parameter binds, as the WDK codec decodes it.
_PERCENT_MAX: ParamValue = TypeAdapter(ParamValue).validate_python(
    {"type": "number-range", "min": 20, "max": 100}
)


def _numbers(*names: str) -> list[WDKParameter]:
    """Parameters as plasmodb types a numeric threshold: a string that is a number."""
    return _PARAMETERS.validate_python(
        [{"name": name, "type": "string", "isNumber": True} for name in names]
    )


def _typed(**types: str) -> list[WDKParameter]:
    return _PARAMETERS.validate_python(
        [{"name": name, "type": kind} for name, kind in types.items()]
    )


def _bounds(
    search_name: str,
    parameters: Sequence[WDKParameter],
    params: Mapping[str, ParamValue],
) -> list[ColumnBound]:
    catalog = column_catalog()
    return column_bounds(
        catalog_search(search_name),
        parameters,
        catalog.attributes or [],
        catalog.searches or [],
        params.get,
    )


def _text(value: str) -> StringValue:
    return StringValue(value=value)


_TM_PARAMETERS = [
    *_typed(organism="multi-pick-vocabulary"),
    *_numbers("min_tm", "max_tm"),
]
_TM: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
    "min_tm": _text("2"),
    "max_tm": _text("99"),
}


def test_each_transmembrane_threshold_is_its_own_bound_on_tm_count() -> None:
    assert _bounds("GenesByTransmembraneDomains", _TM_PARAMETERS, _TM) == [
        ColumnBound(
            column="tm_count",
            display_name="# TM Domains",
            thresholds=(Threshold(2.0, "2"), Threshold(99.0, "99")),
        )
    ]


def test_a_number_range_parameter_is_one_bound_with_both_sides() -> None:
    bounds = _bounds(
        "GenesByIntronJunctions",
        _typed(percent_max="number-range"),
        {"percent_max": _PERCENT_MAX},
    )

    assert {(b.thresholds, b.rivals) for b in bounds} == {
        ((Threshold(20.0, "20", "at_least"), Threshold(100.0, "100", "at_most")), 4)
    }


def test_a_number_parameter_is_a_threshold_with_no_side() -> None:
    assert [
        (b.column, b.thresholds)
        for b in _bounds(
            "GenesByMultiBlast",
            _typed(NumQueryResults="number"),
            {"NumQueryResults": NumberValue(value=100)},
        )
    ] == [("score", (Threshold(100.0, "100"),))]


def test_a_string_the_site_does_not_type_a_number_bounds_nothing() -> None:
    assert (
        _bounds(
            "GenesByMassSpec",
            _typed(min_sequence_count="string", min_spectrum_count="string"),
            {"min_sequence_count": _text("1"), "min_spectrum_count": _text("2")},
        )
        == []
    )


def test_a_column_the_site_gives_no_histogram_is_not_mapped() -> None:
    assert (
        _bounds(
            "GenesByMolecularWeight",
            _numbers("min_molecular_weight", "max_molecular_weight"),
            {
                "min_molecular_weight": _text("0"),
                "max_molecular_weight": _text("200000"),
            },
        )
        == []
    )


def test_the_percentile_thresholds_bound_both_columns_of_the_chosen_samples() -> None:
    bounds = _bounds(
        PERCENTILE_SEARCH,
        [
            *_typed(
                samples_percentile_generic="multi-pick-vocabulary",
                any_or_all="single-pick-vocabulary",
            ),
            *_numbers("min_expression_percentile", "max_expression_percentile"),
        ],
        {
            "samples_percentile_generic": MultiPickValue(
                values=["asexual blood stages", "midgut oocysts"]
            ),
            "min_expression_percentile": _text("80"),
            "max_expression_percentile": _text("100"),
            "any_or_all": SinglePickValue(value="any"),
        },
    )

    assert [(b.column, b.thresholds, b.histogram, b.rivals) for b in bounds] == [
        (
            "min_percentile_chosen",
            (Threshold(80.0, "80"), Threshold(100.0, "100")),
            "min_percentile_chosen-histogram",
            2,
        ),
        (
            "max_percentile_chosen",
            (Threshold(80.0, "80"), Threshold(100.0, "100")),
            "max_percentile_chosen-histogram",
            2,
        ),
    ]


_EXONS = _numbers("num_exons_gte", "num_exons_lte")


def test_every_column_the_exon_search_shows_is_a_rival_for_its_bounds() -> None:
    bounds = _bounds(
        "GenesByExonCount",
        [*_typed(scope="single-pick-vocabulary"), *_EXONS],
        {
            "scope": SinglePickValue(value="Transcript"),
            "num_exons_gte": _text("2"),
            "num_exons_lte": _text("20"),
        },
    )

    assert [(b.column, b.rivals) for b in bounds] == [
        ("gene_exon_count", 3),
        ("gene_transcript_count", 3),
        ("exon_count", 3),
    ]


def _exon_fit(column: str, fitting: int) -> ColumnFit:
    return ColumnFit(
        criterion_id="c_exons",
        criterion_text="two to twenty exons",
        wdk_step_id=7,
        column=column,
        display_name=column,
        bound_value="2 to 20",
        total=500,
        fitting=fitting,
        fitting_at_most=fitting,
    )


def test_rival_columns_stand_only_together() -> None:
    bounds = _bounds(
        "GenesByExonCount",
        _EXONS,
        {"num_exons_gte": _text("2"), "num_exons_lte": _text("20")},
    )
    split = [
        _exon_fit("gene_exon_count", 500),
        _exon_fit("gene_transcript_count", 500),
        _exon_fit("exon_count", 431),
    ]
    agreed = [_exon_fit(b.column, 500) for b in bounds]

    assert settled(list(zip(bounds, split, strict=True))) == []
    assert settled(list(zip(bounds, agreed, strict=True))) == agreed
    assert settled(list(zip(bounds[:2], agreed[:2], strict=True))) == []


def test_the_sole_column_of_a_search_stands_whatever_it_counts() -> None:
    (bound,) = _bounds("GenesByTransmembraneDomains", _TM_PARAMETERS, _TM)
    fit = _exon_fit("tm_count", 12)

    assert settled([(bound, fit)]) == [fit]


def test_a_search_whose_values_are_not_numbers_maps_nothing() -> None:
    assert (
        _bounds(
            "GenesByText",
            _typed(text_expression="string", text_fields="multi-pick-vocabulary"),
            {
                "text_expression": _text("kinase"),
                "text_fields": MultiPickValue(values=["Product"]),
            },
        )
        == []
    )


def test_every_gene_of_the_transmembrane_step_holds_two_to_99_domains() -> None:
    (bound,) = _bounds("GenesByTransmembraneDomains", _TM_PARAMETERS, _TM)

    assert measured(
        bound, by_value_bins(by_value("step_column_tm_count_by_value"))
    ) == Measured(fitting=840, fitting_at_most=840, total=840, bound_value="2 to 99")


def test_one_threshold_alone_is_read_on_the_side_that_holds_every_gene() -> None:
    (bound,) = _bounds(
        "GenesByTransmembraneDomains", _TM_PARAMETERS, {"min_tm": _text("2")}
    )

    assert measured(
        bound, by_value_bins(by_value("step_column_tm_count_by_value"))
    ) == Measured(fitting=840, fitting_at_most=840, total=840, bound_value="2 or more")


def test_a_threshold_with_no_side_the_step_holds_reports_both_sides() -> None:
    (bound,) = _bounds(
        "GenesByTransmembraneDomains", _TM_PARAMETERS, {**_TM, "min_tm": _text("3")}
    )

    assert measured(
        bound, attribute_histogram("step_report_tm_count_histogram").bins()
    ) == Measured(
        fitting=854,
        fitting_at_most=854,
        total=854,
        bound_value="99 or fewer",
        sides=(
            ThresholdSides(
                value="3", above=532, above_at_most=532, below=449, below_at_most=449
            ),
        ),
    )


def test_two_thresholds_on_different_quantities_never_pair() -> None:
    bounds = _bounds(
        "GenesBySecondaryStructure",
        _numbers("min_strand", "min_helix"),
        {"min_strand": _text("10"), "min_helix": _text("5")},
    )
    values = AttributeHistogram(data={"3": 4, "7": 6, "20": 10}).bins()

    assert {b.thresholds for b in bounds} == {
        (Threshold(10.0, "10"), Threshold(5.0, "5"))
    }
    assert measured(bounds[0], values) == Measured(
        fitting=20,
        fitting_at_most=20,
        total=20,
        bound_value="",
        sides=(
            ThresholdSides(
                value="10", above=10, above_at_most=10, below=10, below_at_most=10
            ),
            ThresholdSides(
                value="5", above=16, above_at_most=16, below=4, below_at_most=4
            ),
        ),
    )


def test_a_range_counts_the_records_outside_either_end_as_misfits() -> None:
    (bound, *_) = _bounds(
        "GenesByIntronJunctions",
        _typed(percent_max="number-range"),
        {"percent_max": _PERCENT_MAX},
    )
    values = AttributeHistogram(data={"10": 1, "50": 2, "150": 3}).bins()

    assert measured(bound, values) == Measured(
        fitting=2, fitting_at_most=2, total=6, bound_value="20 to 100"
    )


def test_a_bin_across_the_bound_counts_as_a_range() -> None:
    bound = ColumnBound(
        column="molecular_weight",
        display_name="Molecular Weight",
        thresholds=(
            Threshold(0.0, "0", "at_least"),
            Threshold(200000.0, "200000", "at_most"),
        ),
    )
    bins = by_value_bins(by_value("step_column_molecular_weight_by_value"))

    assert measured(bound, bins) == Measured(
        fitting=708, fitting_at_most=756, total=840, bound_value="0 to 200000"
    )


def test_the_percentile_step_holds_every_transcript_at_80_or_above() -> None:
    bounds = _bounds(
        PERCENTILE_SEARCH,
        _numbers("min_expression_percentile", "max_expression_percentile"),
        {
            "min_expression_percentile": _text("80"),
            "max_expression_percentile": _text("100"),
        },
    )
    histograms = [
        attribute_histogram("step_report_min_percentile_chosen_histogram"),
        attribute_histogram("step_report_max_percentile_chosen_histogram"),
    ]

    assert [measured(b, h.bins()) for b, h in zip(bounds, histograms, strict=True)] == [
        Measured(
            fitting=1663, fitting_at_most=1663, total=1663, bound_value="80 to 100"
        ),
        Measured(
            fitting=1663, fitting_at_most=1663, total=1663, bound_value="80 to 100"
        ),
    ]


def test_a_minimum_equal_to_the_maximum_reads_exactly_that_value() -> None:
    (bound,) = _bounds(
        "GenesByTransmembraneDomains",
        _TM_PARAMETERS,
        {"min_tm": _text("0"), "max_tm": _text("0")},
    )
    every_zero = AttributeHistogram(data={"0": 5041}).bins()

    assert measured(bound, every_zero) == Measured(
        fitting=5041, fitting_at_most=5041, total=5041, bound_value="exactly 0"
    )


def test_a_threshold_every_record_equals_takes_the_side_left_open() -> None:
    (bound,) = _bounds(
        "GenesByTransmembraneDomains",
        _TM_PARAMETERS,
        {"min_tm": _text("0"), "max_tm": _text("5")},
    )
    every_zero = AttributeHistogram(data={"0": 5041}).bins()

    assert measured(bound, every_zero).bound_value == "0 to 5"


def test_a_bound_states_each_side_it_knows() -> None:
    low, high = Threshold(2.0, "2", "at_least"), Threshold(99.0, "99", "at_most")
    same = Threshold(2.0, "2", "at_most")

    assert [
        Bounds(low, high).text,
        Bounds(low, same).text,
        Bounds(low=low).text,
        Bounds(high=high).text,
        Bounds().text,
    ] == ["2 to 99", "exactly 2", "2 or more", "99 or fewer", ""]
