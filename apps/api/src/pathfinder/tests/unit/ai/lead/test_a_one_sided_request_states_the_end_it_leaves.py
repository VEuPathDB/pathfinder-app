from __future__ import annotations

import pytest
from veupathdb.domain.parameters import SinglePickValue

from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.tests.unit.ai.lead._one_sided_rows import (
    bound_value,
    count_of,
    percentile_of,
    range_of,
    step_lines,
    text_value,
)


def test_an_upper_weight_names_the_lower_end_it_leaves_at_the_site_default() -> None:
    lines = step_lines(
        {
            "min_molecular_weight": bound_value(
                text_value("10000"), "default", "Min Molecular Weight"
            ),
            "max_molecular_weight": bound_value(
                text_value("30000"), "stated", "Max Molecular Weight"
            ),
        },
        {
            "max_molecular_weight": count_of(
                "molecular weight", "<", 30, "molecular weight under 30 kDa"
            )
        },
    )

    assert lines == [
        "Min Molecular Weight: 10000",
        "Max Molecular Weight: 30000",
        (
            "The request states 'molecular weight under 30 kDa' and no lower bound. "
            "Site defaults this step holds: Min Molecular Weight 10000"
        ),
    ]


def test_a_lower_isoelectric_point_names_the_upper_end_it_leaves() -> None:
    lines = step_lines(
        {
            "min_isoelectric_point": bound_value(text_value("8"), "stated", "Min pI"),
            "max_isoelectric_point": bound_value(text_value("14"), "default", "Max pI"),
        },
        {
            "min_isoelectric_point": count_of(
                "isoelectric point", ">=", 8, "isoelectric point of at least 8"
            )
        },
    )

    assert lines == [
        "Min pI: 8",
        (
            "The request states 'isoelectric point of at least 8' and no upper bound. "
            "Site defaults this step holds: Max pI 14"
        ),
        "Max pI: 14",
    ]


def test_an_exon_count_at_most_names_the_default_of_two() -> None:
    lines = step_lines(
        {
            "num_exons_gte": bound_value(
                text_value("2"), "default", "Number of exons >="
            ),
            "num_exons_lte": bound_value(
                text_value("4"), "stated", "Number of exons <="
            ),
        },
        {"num_exons_lte": count_of("exons", "<=", 4, "at most 4 exons")},
    )

    assert lines[-1] == (
        "The request states 'at most 4 exons' and no lower bound. "
        "Site defaults this step holds: Number of exons >= 2"
    )


def test_a_bottom_percentile_reads_the_default_of_eighty_as_the_site_s() -> None:
    lines = step_lines(
        {
            "min_expression_percentile": bound_value(
                text_value("80"), "default", "Minimum expression percentile"
            ),
            "max_expression_percentile": bound_value(
                text_value("10"), "stated", "Maximum expression percentile"
            ),
        },
        {
            "max_expression_percentile": percentile_of(
                "bottom", 10, "below the 10th percentile"
            )
        },
    )

    assert lines[-1] == (
        "The request states 'below the 10th percentile' and no lower bound. "
        "Site defaults this step holds: Minimum expression percentile 80. "
        "Minimum expression percentile 80 is above Maximum expression percentile 10. "
        "If these two bound one range, it holds no value as bound, since the low end "
        "is above the high end"
    )


def test_a_top_percentile_names_the_upper_end_it_leaves() -> None:
    lines = step_lines(
        {
            "min_expression_percentile": bound_value(
                text_value("90"), "stated", "Minimum expression percentile"
            ),
            "max_expression_percentile": bound_value(
                text_value("100"), "default", "Maximum expression percentile"
            ),
        },
        {"min_expression_percentile": percentile_of("top", 10, "top 10%")},
    )

    assert lines == [
        "Minimum expression percentile: 90",
        (
            "The request states 'top 10%' and no upper bound. "
            "Site defaults this step holds: Maximum expression percentile 100"
        ),
        "Maximum expression percentile: 100",
    ]


def test_a_search_of_several_pairs_lists_every_default_and_pairs_none() -> None:
    lines = step_lines(
        {
            "occurrences_lower": bound_value(text_value("0"), "default", "SNVs >="),
            "occurrences_upper": bound_value(text_value("5"), "stated", "SNVs <="),
            "dn_ds_ratio_lower": bound_value(text_value("0"), "default", "dN/dS >="),
        },
        {"occurrences_upper": count_of("SNVs", "<=", 5, "at most 5 SNVs")},
    )

    assert lines[2] == (
        "The request states 'at most 5 SNVs' and no lower bound. "
        "Site defaults this step holds: SNVs >= 0, dN/dS >= 0"
    )


def test_a_request_stating_both_sides_adds_nothing() -> None:
    values = {
        "num_exons_gte": bound_value(text_value("3"), "stated", "Number of exons >="),
        "num_exons_lte": bound_value(text_value("6"), "stated", "Number of exons <="),
        "gene_type": bound_value(text_value("20"), "default", "Other number"),
    }

    lines = step_lines(
        values,
        {
            "num_exons_gte": count_of("exons", ">=", 3, "3 to 6 exons"),
            "num_exons_lte": count_of("exons", "<=", 6, "3 to 6 exons"),
        },
    )

    assert lines == [
        "Number of exons >=: 3",
        "Number of exons <=: 6",
        "Other number: 20",
    ]


def test_a_request_stating_no_bound_on_the_range_adds_nothing() -> None:
    lines = step_lines(
        {
            "min_molecular_weight": bound_value(
                text_value("10000"), "default", "Min Molecular Weight"
            ),
            "max_molecular_weight": bound_value(
                text_value("50000"), "default", "Max Molecular Weight"
            ),
        },
        {},
    )

    assert lines == ["Min Molecular Weight: 10000", "Max Molecular Weight: 50000"]


def test_an_exact_value_states_no_side() -> None:
    lines = step_lines(
        {
            "chromosome": bound_value(text_value("17"), "stated", "Chromosome"),
            "other": bound_value(text_value("5"), "default", "Other number"),
        },
        {"chromosome": count_of("chromosome", "=", 17, "on chromosome 17")},
    )

    assert lines == ["Chromosome: 17", "Other number: 5"]


@pytest.mark.parametrize(
    "other",
    [
        bound_value(text_value("kinase"), "default", "Other", number=False),
        bound_value(text_value("7"), "default", "Other", number=False),
        bound_value(SinglePickValue(value="3"), "default", "Other"),
        bound_value(text_value("7"), "default", "Other", visible=False),
        bound_value(text_value("7"), "chosen", "Other"),
        bound_value(text_value(""), "default", "Other"),
        bound_value(text_value("7"), "default", "Other").model_copy(
            update={"placeholder": True}
        ),
    ],
    ids=["text", "not-a-number", "pick", "hidden", "chosen", "empty", "placeholder"],
)
def test_only_a_shown_number_at_the_site_default_is_listed(other: BoundValue) -> None:
    lines = step_lines(
        {"max_x": bound_value(text_value("5"), "stated", "Max X"), "other": other},
        {"max_x": count_of("x", "<=", 5, "x at most 5")},
    )

    assert [line for line in lines if "Site defaults" in line] == []


def test_a_requirement_the_thread_no_longer_holds_adds_nothing() -> None:
    lines = step_lines(
        {
            "min_x": bound_value(text_value("1"), "default", "Min X"),
            "max_x": bound_value(text_value("5"), "stated", "Max X"),
        },
        {"max_x": count_of("x", "<=", 5, "x at most 5")},
        held=[count_of("y", "<=", 7, "y at most 7")],
    )

    assert lines == ["Min X: 1", "Max X: 5"]


def test_a_link_to_a_parameter_the_step_does_not_hold_adds_nothing() -> None:
    lines = step_lines(
        {"min_x": bound_value(text_value("1"), "default", "Min X")},
        {"max_x": count_of("x", "<=", 5, "x at most 5")},
    )

    assert lines == ["Min X: 1"]


def test_a_linked_value_at_the_default_is_not_listed_among_the_defaults() -> None:
    lines = step_lines(
        {
            "min_x": bound_value(text_value("1"), "default", "Min X"),
            "max_x": bound_value(text_value("5"), "default", "Max X"),
        },
        {"max_x": count_of("x", "<=", 5, "x at most 5")},
    )

    assert lines[-1] == (
        "The request states 'x at most 5' and no lower bound. "
        "Site defaults this step holds: Min X 1"
    )


_CROSSED = (
    "If these two bound one range, it holds no value as bound, since the low end "
    "is above the high end"
)


def test_a_stated_low_end_above_a_default_high_end_says_so() -> None:
    lines = step_lines(
        {
            "min_weight": bound_value(text_value("60000"), "stated", "Min Weight"),
            "max_weight": bound_value(text_value("50000"), "default", "Max Weight"),
        },
        {"min_weight": count_of("weight", ">", 60000, "over 60000")},
    )

    assert lines[1] == (
        "The request states 'over 60000' and no upper bound. "
        "Site defaults this step holds: Max Weight 50000. "
        f"Min Weight 60000 is above Max Weight 50000. {_CROSSED}"
    )


def test_each_default_past_the_stated_end_is_named() -> None:
    lines = step_lines(
        {
            "a": bound_value(text_value("20"), "default", "A"),
            "b": bound_value(text_value("30"), "default", "B"),
            "c": bound_value(text_value("2"), "default", "C"),
            "max_x": bound_value(text_value("10"), "stated", "Max X"),
        },
        {"max_x": count_of("x", "<=", 10, "x at most 10")},
    )

    assert lines[-1] == (
        "The request states 'x at most 10' and no lower bound. "
        "Site defaults this step holds: A 20, B 30, C 2. "
        f"A 20 is above Max X 10. {_CROSSED}. B 30 is above Max X 10. {_CROSSED}"
    )


def test_ends_that_meet_do_not_cross() -> None:
    lines = step_lines(
        {
            "min_x": bound_value(text_value("10"), "default", "Min X"),
            "max_x": bound_value(text_value("10"), "stated", "Max X"),
        },
        {"max_x": count_of("x", "<=", 10, "x at most 10")},
    )

    assert lines[-1] == (
        "The request states 'x at most 10' and no lower bound. "
        "Site defaults this step holds: Min X 10"
    )


def test_a_linked_value_with_no_number_has_no_end_to_cross() -> None:
    lines = step_lines(
        {
            "min_x": bound_value(text_value("10"), "default", "Min X"),
            "max_x": bound_value(text_value("many"), "stated", "Max X"),
        },
        {"max_x": count_of("x", "<=", 5, "x at most 5")},
    )

    assert lines[-1] == (
        "The request states 'x at most 5' and no lower bound. "
        "Site defaults this step holds: Min X 10"
    )


def test_a_default_range_is_not_read_as_a_crossing_end() -> None:
    lines = step_lines(
        {
            "percent_max": bound_value(range_of(20, 100), "default", "Percent"),
            "max_x": bound_value(text_value("5"), "stated", "Max X"),
        },
        {"max_x": count_of("x", "<=", 5, "x at most 5")},
    )

    assert lines[-1] == (
        "The request states 'x at most 5' and no lower bound. "
        "Site defaults this step holds: Percent 20 to 100"
    )
