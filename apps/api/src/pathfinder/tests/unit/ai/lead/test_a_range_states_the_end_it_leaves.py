from __future__ import annotations

from veupathdb.domain.parameters import param_value_from_raw

from pathfinder.ai.lead.parameter_facts import step_parameters
from pathfinder.domain.strategy.operational_spec import Criterion, RequirementLink
from pathfinder.tests.unit.ai.lead._one_sided_rows import (
    bound_value,
    count_of,
    range_of,
    step_lines,
    text_value,
)


def test_a_range_at_its_published_limit_says_so() -> None:
    lines = step_lines(
        {
            "percent_max": bound_value(
                range_of(1, 50),
                "chosen",
                "Percent of MAI",
                published=(1, 100),
            )
        },
        {"percent_max": count_of("percent of MAI", "<=", 50, "at most 50% of MAI")},
    )

    assert lines[-1] == (
        "The request states 'at most 50% of MAI' and no lower bound. "
        "The low end is the site's published minimum, 1"
    )


def test_a_range_lower_bound_at_its_published_limit_says_so() -> None:
    lines = step_lines(
        {
            "percent_max": bound_value(
                range_of(30, 100),
                "chosen",
                "Percent of MAI",
                published=(1, 100),
            )
        },
        {"percent_max": count_of("percent of MAI", ">=", 30, "at least 30% of MAI")},
    )

    assert lines[-1] == (
        "The request states 'at least 30% of MAI' and no upper bound. "
        "The high end is the site's published maximum, 100"
    )


def test_a_range_with_no_published_limit_names_the_end_it_holds() -> None:
    lines = step_lines(
        {"period": bound_value(range_of(20, 25), "chosen", "Rhythm period")},
        {"period": count_of("period", "<=", 25, "a period up to 25")},
    )

    assert lines[-1] == (
        "The request states 'a period up to 25' and no lower bound. "
        "The low end holds 20, which the request does not state"
    )


def test_a_range_stating_both_sides_adds_nothing() -> None:
    criterion = Criterion(
        id="c1",
        text="the criterion",
        search_name="ASearch",
        answers=[],
        resolved_params={
            "percent_max": bound_value(
                range_of(30, 50),
                "stated",
                "Percent of MAI",
                published=(1, 100),
            )
        },
    )
    low = count_of("percent of MAI", ">=", 30, "30 to 50%")
    high = count_of("percent of MAI", "<=", 50, "30 to 50%")
    linked = criterion.model_copy(
        update={
            "answers": [
                RequirementLink(requirement=low.id, param="percent_max"),
                RequirementLink(requirement=high.id, param="percent_max"),
            ]
        }
    )

    [row] = step_parameters(linked, "gene", [], [low, high])

    assert row.notes == []


def test_a_default_range_is_listed_with_its_ends() -> None:
    lines = step_lines(
        {
            "min_total_unique": bound_value(
                text_value("30"), "stated", "Unique reads >="
            ),
            "percent_max": bound_value(range_of(20, 100), "default", "Percent of MAI"),
        },
        {"min_total_unique": count_of("unique reads", ">=", 30, "30 unique reads")},
    )

    assert lines[1] == (
        "The request states '30 unique reads' and no upper bound. "
        "Site defaults this step holds: Percent of MAI 20 to 100"
    )


def test_a_range_holding_one_end_says_the_other_is_open() -> None:
    criterion = Criterion(
        id="c1",
        text="the criterion",
        search_name="ASearch",
        resolved_params={
            "period": bound_value(
                param_value_from_raw({"max": 25}, "number-range"), "chosen", "Period"
            )
        },
    )
    held = count_of("period", "<=", 25, "a period up to 25")
    linked = criterion.model_copy(
        update={"answers": [RequirementLink(requirement=held.id, param="period")]}
    )

    [row] = step_parameters(linked, "gene", [], [held])

    assert row.notes == [
        (
            "The request states 'a period up to 25' and no lower bound. "
            "The range leaves its low end open"
        )
    ]


def test_a_linked_range_names_its_own_end_and_no_other_default() -> None:
    criterion = Criterion(
        id="c1",
        text="the criterion",
        search_name="ASearch",
        resolved_params={
            "percent_max": bound_value(
                range_of(1, 50), "chosen", "Percent of MAI", published=(1, 100)
            ),
            "min_total_unique": bound_value(
                text_value("20"), "default", "Unique reads >="
            ),
        },
    )
    held = count_of("percent of MAI", "<=", 50, "at most 50% of MAI")
    linked = criterion.model_copy(
        update={"answers": [RequirementLink(requirement=held.id, param="percent_max")]}
    )

    [range_row, _] = step_parameters(linked, "gene", [], [held])

    assert range_row.notes == [
        (
            "The request states 'at most 50% of MAI' and no lower bound. "
            "The low end is the site's published minimum, 1"
        )
    ]
