"""The count of narrowing values no step row of the facts carries."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.domain.value_caveats import ValueCaveat


def uncarried_assumptions(
    caveats: Sequence[ValueCaveat], facts: TurnFacts | None
) -> int:
    """How many values the request did not state, and that narrow their step,
    no step row shows with who set them and their measurement."""
    narrowing = [c for c in caveats if c.kind == "assumed_value"]
    return sum(1 for c in narrowing if facts is None or not facts.carries(c))
