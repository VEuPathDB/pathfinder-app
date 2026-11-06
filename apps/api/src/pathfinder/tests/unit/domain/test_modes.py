from __future__ import annotations

from pathfinder.domain.modes import (
    BUILD_PROBABILITY_FLOOR,
    EXPLORE_PHASE,
    route_of_build_probability,
    route_of_parked_phase,
)


def test_build_needs_the_floor() -> None:
    assert route_of_build_probability(0.65) == "build"
    assert route_of_build_probability(0.6499) == "explore"
    assert BUILD_PROBABILITY_FLOOR == 0.65


def test_no_probability_is_explore() -> None:
    assert route_of_build_probability(None) == "explore"


def test_a_park_returns_to_its_agent() -> None:
    assert route_of_parked_phase(EXPLORE_PHASE) == "explore"
    assert [
        route_of_parked_phase(p) for p in ("lead", "frame", "build", "verification")
    ] == ["build"] * 4
