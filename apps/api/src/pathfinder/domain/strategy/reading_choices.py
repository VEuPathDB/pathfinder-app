from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.domain.strategy.operational_spec import Criterion, ValueSource
from pathfinder.domain.strategy.readings import ReadingChooser

CHOSEN_BY: dict[ReadingChooser, str] = {
    ReadingChooser.RESEARCHER_ON_A_CARD: "picked by the researcher on a card",
    ReadingChooser.ASSISTANT: "chosen by you; no card answer of the researcher picked it",
}

VALUE_SET_BY: dict[ValueSource, str] = {
    "stated": "stated by the researcher",
    "card": "picked by the researcher on a card",
    "chosen": "chosen by you",
    "default": "the site's default",
    "held": "held by the strategy as it stood",
}


def _named_line(named: ChosenReading, picked: Sequence[str]) -> str:
    on_card = next((label for label in named.labels() if label in picked), None)
    if on_card is not None:
        return f"- '{on_card}': {CHOSEN_BY[ReadingChooser.RESEARCHER_ON_A_CARD]}"
    others = ", ".join(f"'{label}'" for label in named.alternatives)
    return (
        f"- '{named.chosen}': {CHOSEN_BY[ReadingChooser.ASSISTANT]}; "
        f"other readings: {others}"
    )


def reading_choice_lines(
    criteria: Sequence[Criterion],
    named: Sequence[ChosenReading],
    picked: Sequence[str],
) -> list[str]:
    return [
        *(
            f"- {c.id} reads '{held.reading}': {CHOSEN_BY[held.chosen_by]}"
            for c in criteria
            if (held := c.held_reading) is not None
        ),
        *(_named_line(reading, picked) for reading in named),
    ]


__all__ = ["CHOSEN_BY", "VALUE_SET_BY", "reading_choice_lines"]
