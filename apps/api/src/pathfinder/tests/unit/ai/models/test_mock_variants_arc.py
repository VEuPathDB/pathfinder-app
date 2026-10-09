"""The variants arc reads the live strategy and compares two variants of a
search one of its steps runs."""

from __future__ import annotations

import pytest

from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play

_SIGNAL = "GenesWithSignalPeptide"
_TEXT = "GenesByText"


def _live(*searches: str) -> dict[str, object]:
    return {
        "steps": [
            {"step_id": f"step_{i}", "search_name": search, "is_root": i == 0}
            for i, search in enumerate(searches)
        ]
    }


@pytest.mark.parametrize(
    ("held", "compared"),
    [((_SIGNAL,), _SIGNAL), ((_TEXT, _SIGNAL), _TEXT)],
)
def test_the_variants_vary_a_search_the_strategy_runs(
    held: tuple[str, ...], compared: str
) -> None:
    scene = Scene(answers={"get_live_strategy_state": _live(*held)})

    calls = play("lead", "plasmodb", "Compare them [[arc:variants]]", scene=scene)
    [compare] = args_of(calls, "compare_search_variants")

    assert names(calls) == [
        "classify_user_intent",
        "get_live_strategy_state",
        "compare_search_variants",
        "final_result",
    ]
    assert {v["search_name"] for v in compare["variants"]} == {compared}
    assert len(compare["variants"]) == 2
