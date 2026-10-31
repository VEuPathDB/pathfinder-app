from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.reading_choices import reading_choice_lines
from pathfinder.domain.strategy.readings import (
    AcceptedReading,
    ReadingChooser,
    ReadValues,
)

_SHARE = "PLAS>=55T"
_LABEL = "At least 55 of the 61 genomes"
_PARAM = "phyletic_expression"
_STRAIN = "strain-level counts"
_SPECIES = "species-collapsed counts"
_BY_YOU = "chosen by you; no card answer of the researcher picked it"


def _read() -> ReadValues:
    return ReadValues(criterion_id="c_plas", params={_PARAM: _SHARE}, reading=_LABEL)


def _criterion(chooser: ReadingChooser) -> Criterion:
    return Criterion(
        id="c_plas",
        text="present in Plasmodium",
        resolved_params={
            _PARAM: BoundValue(value=StringValue(value=_SHARE), source="card")
        },
        accepted_reading=_read().accepted(chooser),
    )


def test_an_accepted_reading_carries_who_chose_it() -> None:
    chosen = [
        _read().accepted(chooser).chosen_by
        for chooser in (ReadingChooser.RESEARCHER_ON_A_CARD, ReadingChooser.ASSISTANT)
    ]

    assert chosen == [ReadingChooser.RESEARCHER_ON_A_CARD, ReadingChooser.ASSISTANT]


def test_a_reading_with_no_recorded_chooser_is_the_assistants() -> None:
    held = AcceptedReading.model_validate(
        {"reading": _LABEL, "params": {_PARAM: _SHARE}}
    )

    assert held.chosen_by is ReadingChooser.ASSISTANT


def test_a_held_reading_names_who_chose_it() -> None:
    lines = [
        reading_choice_lines([_criterion(chooser)], [], [])
        for chooser in (ReadingChooser.RESEARCHER_ON_A_CARD, ReadingChooser.ASSISTANT)
    ]

    assert lines == [
        [f"- c_plas reads '{_LABEL}': picked by the researcher on a card"],
        [f"- c_plas reads '{_LABEL}': {_BY_YOU}"],
    ]


def test_a_reading_a_pass_built_without_asking_is_the_assistants() -> None:
    named = ChosenReading(chosen=_STRAIN, alternatives=[_SPECIES])

    assert reading_choice_lines([], [named], []) == [
        f"- '{_STRAIN}': {_BY_YOU}; other readings: '{_SPECIES}'"
    ]


def test_a_named_reading_picked_on_a_card_is_the_researchers() -> None:
    named = ChosenReading(chosen=_STRAIN, alternatives=[_SPECIES])

    assert reading_choice_lines([], [named], [_SPECIES]) == [
        f"- '{_SPECIES}': picked by the researcher on a card"
    ]
