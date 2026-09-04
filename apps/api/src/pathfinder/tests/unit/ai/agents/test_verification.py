"""VERIFY states where a number in its prose is allowed to come from."""

from __future__ import annotations

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS


def _normalized(text: str) -> str:
    """The instructions wrap, so a phrase is asserted without its line breaks."""
    return " ".join(text.split())


def test_a_numeric_parameter_is_restated_only_from_the_constraint_report() -> None:
    assert (
        "A numeric parameter is restated ONLY from its ``constraint_report`` "
        "entry. Write the bound value and the realized reading that entry "
        "carries; never add an interpretation of your own next to a number "
        '("80 (top 10%)"). An entry whose status is substituted is a '
        "deviation: report the realized reading, set ``honored=False``, and "
        "carry it into ``caveats``."
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_verification_instructions_are_ascii() -> None:
    assert _VERIFICATION_INSTRUCTIONS.isascii()
