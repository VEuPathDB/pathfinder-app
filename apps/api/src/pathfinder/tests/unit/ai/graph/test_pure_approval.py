"""What a typed reply has to be to count as clicking Approve."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph._lead_answers import MAX_APPROVAL_LENGTH, is_pure_approval


@pytest.mark.parametrize(
    "text",
    ["yes", "  OK. ", "sure", "go ahead", "run it", "sounds good", "yes, go ahead"],
)
def test_an_approval_phrase_and_nothing_else_approves(text: str) -> None:
    assert is_pure_approval(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no",
        "yes but use the 3D7 organism instead",
        "ok now delete the second step",
        "y" * (MAX_APPROVAL_LENGTH + 1),
    ],
)
def test_anything_that_carries_an_instruction_does_not_approve(text: str) -> None:
    assert is_pure_approval(text) is False
