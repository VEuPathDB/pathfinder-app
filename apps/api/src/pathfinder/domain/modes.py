from __future__ import annotations

from typing import Final, Literal

type ThreadMode = Literal["auto", "explore", "build"]
type TurnRoute = Literal["explore", "build"]

EXPLORE_PHASE: Final = "explore"
READINGS_PHASE: Final = "readings"
BUILD_PROBABILITY_FLOOR: Final = 0.65


def route_of_build_probability(probability: float | None) -> TurnRoute:
    if probability is not None and probability >= BUILD_PROBABILITY_FLOOR:
        return "build"
    return "explore"


def route_of_parked_phase(phase: str) -> TurnRoute:
    return "explore" if phase == EXPLORE_PHASE else "build"
