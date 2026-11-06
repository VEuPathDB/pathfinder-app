"""A step title labels the half of a radio pair that carries the criterion."""

from __future__ import annotations

from veupathdb.domain.parameters import SinglePickValue, StringValue
from veupathdb_mcp.catalog import RADIO_OFF

from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.step_naming import (
    StepTitle,
    TitleLabel,
    criterion_title,
)

_PAIRS = {"ec_number_pattern": "ec_wildcard"}


def _criterion(pick: str, label: str, wildcard: str, *, paired: bool) -> Criterion:
    return Criterion(
        id="c1",
        text="all enzymes",
        search_name="GenesByEcNumber",
        search_display_name="EC Number",
        radio_pairs=_PAIRS if paired else {},
        resolved_params={
            "ec_number_pattern": BoundValue(
                value=SinglePickValue(value=pick), source="chosen", label=label
            ),
            "ec_wildcard": BoundValue(
                value=StringValue(value=wildcard),
                source="chosen",
                at_default=wildcard == RADIO_OFF,
            ),
        },
    )


def test_a_switched_off_pick_gives_way_to_the_free_text_value() -> None:
    title = criterion_title(_criterion(RADIO_OFF, RADIO_OFF, "*", paired=True))

    assert title == StepTitle(
        head="EC Number",
        labels=[TitleLabel(param="ec_wildcard", wire="*", label="*")],
    )
    assert title.name == "EC Number: *"


def test_a_pick_with_the_free_text_off_keeps_its_label() -> None:
    title = criterion_title(
        _criterion("3.4.-.-", "3.4.-.- (peptidases)", RADIO_OFF, paired=True)
    )

    assert title.name == "EC Number: 3.4.-.- (peptidases)"


def test_a_search_that_declares_no_pair_labels_its_picks_alone() -> None:
    title = criterion_title(_criterion(RADIO_OFF, RADIO_OFF, "*", paired=False))

    assert title.name == "EC Number: N/A"


def test_the_free_text_label_leaves_when_its_value_moves() -> None:
    title = criterion_title(_criterion(RADIO_OFF, RADIO_OFF, "*", paired=True))

    kept = title.kept(
        {
            "ec_number_pattern": SinglePickValue(value=RADIO_OFF),
            "ec_wildcard": StringValue(value="2.7.*"),
        }
    )

    assert kept.name == "EC Number"
