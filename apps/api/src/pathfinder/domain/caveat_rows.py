"""Which caveats a step row or a column row of the facts already draws."""

from __future__ import annotations

from pathfinder.domain.caveats import Caveat, PhraseCaveat, SampleCaveat
from pathfinder.domain.value_caveats import (
    AssumedValueCaveat,
    ChoiceCaveat,
    UnmeasuredValueCaveat,
)


def sampled_column(caveat: Caveat) -> tuple[int, str] | None:
    match caveat:
        case SampleCaveat():
            return caveat.fit.column_key
        case _:
            return None


def drawn_by_a_row(caveat: Caveat, noted: set[tuple[str, str]]) -> bool:
    match caveat:
        case (
            AssumedValueCaveat()
            | UnmeasuredValueCaveat()
            | ChoiceCaveat()
            | PhraseCaveat()
        ):
            return (caveat.criterion_id, caveat.param_display_name) in noted
        case _:
            return False


__all__ = ["drawn_by_a_row", "sampled_column"]
