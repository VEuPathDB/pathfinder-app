"""A value the request did not state that narrows the result is a caveat, with
the count at the value and the count the site measured for the other reading."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, StringValue

from pathfinder.domain.caveats import caveats_for
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    MeasurementKind,
    OperationalSpec,
    ValueSource,
)
from pathfinder.domain.value_caveats import (
    AssumedValueCaveat,
    UnmeasuredValueCaveat,
    assumed_value_caveats,
)

_PERCENTILE = "min_expression_percentile"
_LOOSEST = Measurement(kind="loosest_bound", param=_PERCENTILE, count=5120, reading="0")


def _spec(
    source: ValueSource,
    measurement: Measurement = _LOOSEST,
    result_count: int | None = 1024,
) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_expr",
                text="expressed in blood stages",
                search_name="GenesByRNASeqPercentile",
                resolved_params={
                    _PERCENTILE: BoundValue(value=NumberValue(value=80), source=source)
                },
                param_display_names={_PERCENTILE: "Minimum expression percentile"},
                measurements=[measurement],
                result_count=result_count,
            )
        ]
    )


def test_a_default_that_narrows_is_a_caveat_with_both_counts() -> None:
    caveats = assumed_value_caveats(_spec("default"))

    assert caveats == [
        AssumedValueCaveat(
            criterion_id="c_expr",
            param_display_name="Minimum expression percentile",
            value="80",
            source="default",
            bound_count=1024,
            reading_kind="loosest_bound",
            reading="0",
            reading_count=5120,
        )
    ]
    assert caveats[0].sentence == (
        "Minimum expression percentile is 80, the site's default: 1,024 genes at "
        "that value, 5,120 at 0"
    )


def test_a_chosen_value_that_narrows_is_a_caveat() -> None:
    wildcard = Measurement(
        kind="wildcard_phrase", param=_PERCENTILE, count=216, reading="VSP*"
    )

    (caveat,) = assumed_value_caveats(_spec("chosen", wildcard, result_count=20))

    assert caveat.sentence == (
        "Minimum expression percentile is 80, chosen: 20 genes at that value, "
        "216 for VSP*"
    )


def test_a_stated_card_or_held_value_is_never_a_caveat() -> None:
    assert [assumed_value_caveats(_spec(s)) for s in ("stated", "card", "held")] == [
        [],
        [],
        [],
    ]


def test_a_value_the_other_reading_does_not_widen_is_no_caveat() -> None:
    same = Measurement(kind="loosest_bound", param=_PERCENTILE, count=1024)

    assert assumed_value_caveats(_spec("default", same)) == []


def test_a_value_with_no_count_is_no_caveat() -> None:
    assert assumed_value_caveats(_spec("default", result_count=None)) == []


def test_a_measurement_of_another_param_is_no_caveat() -> None:
    other = Measurement(kind="loosest_bound", param="max_percentile", count=9000)

    assert assumed_value_caveats(_spec("default", other)) == []


def test_every_counted_kind_names_its_reading() -> None:
    readings: list[tuple[MeasurementKind, str]] = [
        ("loosest_bound", "0"),
        ("wildcard_phrase", "VSP*"),
        ("site_search_reach", '"VSP"'),
        ("any_strain", "at least one of 15 species"),
        ("all_strains", "all 15 species"),
    ]
    endings = [
        assumed_value_caveats(
            _spec(
                "chosen",
                Measurement(kind=kind, param=_PERCENTILE, count=2000, reading=read),
            )
        )[0].sentence.rsplit(", ", 1)[1]
        for kind, read in readings
    ]

    assert endings == [
        "2,000 at 0",
        "2,000 for VSP*",
        '2,000 that the site search finds for "VSP"',
        "2,000 with an ortholog in at least one of 15 species",
        "2,000 with an ortholog in all 15 species",
    ]


def test_a_criterion_with_no_display_name_names_the_parameter() -> None:
    spec = _spec("default")
    spec.criteria[0].param_display_names = {}

    assert assumed_value_caveats(spec)[0].param_display_name == _PERCENTILE


def test_a_pick_from_a_cut_list_is_no_caveat() -> None:
    """The row names how much of the vocabulary the pick was taken from."""
    cut = Measurement(
        kind="picked_from_a_cut_list", param=_PERCENTILE, count=50, unchosen_count=16
    )

    assert assumed_value_caveats(_spec("chosen", cut)) == []


def test_a_label_measurement_is_no_caveat() -> None:
    label = Measurement(kind="vocabulary_label", param=_PERCENTILE, label="80th")

    assert assumed_value_caveats(_spec("chosen", label)) == []


def test_the_caveats_for_a_spec_follow_the_measured_ones() -> None:
    measured = assumed_value_caveats(_spec("chosen"))
    spec = _spec("default")

    assert caveats_for(spec, measured) == [*measured, *assumed_value_caveats(spec)]


def test_a_vocabulary_value_is_shown_by_its_term() -> None:
    spec = OperationalSpec(
        criteria=[
            Criterion(
                id="c_text",
                text="variant surface proteins",
                resolved_params={
                    "text_expression": BoundValue(
                        value=StringValue(value="variant surface protein"),
                        source="chosen",
                        basis="the product name",
                    )
                },
                measurements=[
                    Measurement(
                        kind="wildcard_phrase", param="text_expression", count=216
                    )
                ],
                result_count=20,
            )
        ]
    )

    assert assumed_value_caveats(spec)[0].value == "variant surface protein"


def test_a_default_whose_reading_did_not_arrive_says_it_was_not_measured() -> None:
    unread = Measurement(kind="loosest_bound", param=_PERCENTILE, reading="0")

    caveats = assumed_value_caveats(_spec("default", unread))

    assert caveats == [
        UnmeasuredValueCaveat(
            criterion_id="c_expr",
            param_display_name="Minimum expression percentile",
            value="80",
            source="default",
            reading_kind="loosest_bound",
            reading="0",
        )
    ]
    assert caveats[0].sentence == (
        "Minimum expression percentile is 80, the site's default: its effect was "
        "not measured, since the count at 0 did not arrive"
    )


def test_a_chosen_value_whose_reading_did_not_arrive_is_a_caveat_too() -> None:
    unread = Measurement(
        kind="any_strain",
        param=_PERCENTILE,
        reading="at least one of 15 species",
    )

    (caveat,) = assumed_value_caveats(_spec("chosen", unread, result_count=None))

    assert caveat.sentence == (
        "Minimum expression percentile is 80, chosen: its effect was not measured, "
        "since the count with an ortholog in at least one of 15 species did not "
        "arrive"
    )


def test_a_stated_value_whose_reading_did_not_arrive_is_no_caveat() -> None:
    unread = Measurement(kind="loosest_bound", param=_PERCENTILE, reading="0")

    assert assumed_value_caveats(_spec("stated", unread)) == []
