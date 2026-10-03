"""A number value the researcher did not state shows the decimals of the
parameter's published initial value, never more than four significant digits,
and four significant digits where those decimals would show zero."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    NumberValue,
    ParamValue,
    SinglePickValue,
    StringValue,
    VocabOption,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.strategy.value_binding import bind_values

# tritrypdb RNA-Seq fold change: the floor is a pick whose terms are the
# TPM a read count gives, and whose initial term is the ten reads one.
_TEN_READS = "3386.468221526066315665759866396624601158"
_FLOOR = ParameterInfo(
    name="hard_floor",
    display_name="Floor =",
    type="single-pick-vocabulary",
    required=True,
    is_visible=True,
    help="",
    value_format="",
    default_value=_TEN_READS,
    allowed_values=[
        VocabOption(value=_TEN_READS, display="10 reads"),
        VocabOption(value="734.0197714535435", display="10 reads"),
    ],
)


def _number(initial: str | None) -> ParameterInfo:
    return ParameterInfo(
        name="fold_change",
        display_name="Fold change >=",
        type="string",
        required=True,
        is_visible=True,
        help="",
        value_format="",
        is_number=True,
        default_value=initial,
    )


def _shown(
    value: ParamValue, info: ParameterInfo, source: ValueSource = "chosen"
) -> str | None:
    return bind_values({info.name: value}, source, [info])[info.name].rounded()


def test_a_long_decimal_shows_the_integers_an_integer_initial_value_shows() -> None:
    assert _shown(StringValue(value="734.0197714535435"), _number("10")) == "734"


def test_a_long_initial_term_still_caps_a_pick_at_four_significant_digits() -> None:
    assert _shown(SinglePickValue(value="734.0197714535435"), _FLOOR) == "734"


def test_a_value_the_decimals_would_show_as_zero_keeps_four_digits() -> None:
    assert _shown(StringValue(value="0.001234"), _number("0.05")) == "0.001234"


def test_a_value_shows_the_decimals_of_the_initial_value() -> None:
    assert _shown(StringValue(value="0.04871"), _number("0.05")) == "0.05"


def test_a_number_with_no_initial_value_shows_four_significant_digits() -> None:
    assert _shown(NumberValue(value=0.0012345678), _number(None)) == "0.001235"


def test_an_integer_value_under_an_integer_initial_value_is_unchanged() -> None:
    assert _shown(NumberValue(value=25), _number("10")) == "25"


def test_a_value_the_researcher_states_shows_as_written() -> None:
    assert [_shown(StringValue(value="734.0197"), _number("10"), "stated")] == [None]


def test_a_text_is_no_number_to_round() -> None:
    text = ParameterInfo(
        name="text_expression",
        display_name="Text term",
        type="string",
        required=True,
        is_visible=True,
        help="",
        value_format="",
    )

    assert [_shown(StringValue(value="3.14159"), text)] == [None]
