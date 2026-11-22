from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from veupathdb.domain.parameters import ParamValue, shown_stated_text

from strategist.tests.unit.ai.tools._binding_card_path import card_pick
from strategist.tests.unit.ai.tools._binding_paths import (
    HELD_CHILDREN,
    SAMPLES,
    Case,
    Outcome,
    build,
    control_test,
    edit,
    frame,
    options,
    typed_operation,
    variant,
)

PATHS: dict[
    str, Callable[[pytest.MonkeyPatch, Case, ParamValue], Awaitable[Outcome]]
] = {
    "frame_rebind": frame,
    "variant": variant,
    "update_leaf_params": edit,
    "typed_operation": typed_operation,
    "options_read": options,
    "card_pick": card_pick,
}
STATES_EVERY_VALUE: dict[
    str, Callable[[pytest.MonkeyPatch, Case, ParamValue], Awaitable[Outcome]]
] = {"build_strategy": build, "control_test": control_test}
BINDS_THE_CHILD = frozenset(
    {"frame_rebind", "update_leaf_params", "typed_operation", "card_pick"}
)


@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize(
    "case", ["given_back", "left_out", "stated_anew", "other_case", "other_writing"]
)
@pytest.mark.parametrize("held", sorted(HELD_CHILDREN))
async def test_every_binding_path_reads_a_held_child_alike(
    monkeypatch: pytest.MonkeyPatch, path: str, case: Case, held: str
) -> None:
    child = HELD_CHILDREN[held]

    outcome = await PATHS[path](monkeypatch, case, child)

    match case:
        case "given_back" | "left_out":
            assert outcome.kind == "moved", outcome.text
            assert (
                f"{SAMPLES}, which held {shown_stated_text(child)}, was read again"
                in outcome.text
            )
        case "stated_anew":
            assert (outcome.kind, "No such dataset" in outcome.text) == (
                "refused",
                True,
            ), outcome.text
        case "other_case" | "other_writing":
            assert outcome.kind == "accepted", outcome.text
            if path in BINDS_THE_CHILD:
                assert outcome.child == child


@pytest.mark.parametrize("path", sorted(STATES_EVERY_VALUE))
@pytest.mark.parametrize(
    "case", ["given_back", "left_out", "stated_anew", "other_case", "other_writing"]
)
@pytest.mark.parametrize("held", sorted(HELD_CHILDREN))
async def test_a_path_that_holds_nothing_reads_every_value_it_states(
    monkeypatch: pytest.MonkeyPatch, path: str, case: Case, held: str
) -> None:
    outcome = await STATES_EVERY_VALUE[path](monkeypatch, case, HELD_CHILDREN[held])

    match case:
        case "given_back" | "stated_anew":
            assert (outcome.kind, "was read again" in outcome.text) == (
                "refused",
                False,
            ), outcome.text
        case "left_out" | "other_case" | "other_writing":
            assert (outcome.kind, outcome.child) == ("accepted", None), outcome.text
