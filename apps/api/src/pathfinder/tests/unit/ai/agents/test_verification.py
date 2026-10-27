from __future__ import annotations

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.graph.state import VerificationDigest


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_verification_instructions_are_ascii() -> None:
    assert _VERIFICATION_INSTRUCTIONS.isascii()


def test_the_checks_on_the_site_decide_the_verdict() -> None:
    assert (
        "Those checks decide the verdict. You never decide it, and nothing you "
        "write changes it."
    ) in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_the_prose_states_no_verdict_of_its_own() -> None:
    assert "State no verdict of your own." in _normalized(_VERIFICATION_INSTRUCTIONS)


def test_a_control_test_runs_only_on_a_set_attached_to_the_conversation() -> None:
    instructions = _normalized(_VERIFICATION_INSTRUCTIONS)

    assert (
        "A control test runs only on a control set attached to this conversation, "
        "named by the id ``list_control_sets`` gives it."
    ) in instructions
    assert "With no attached set, run no control test." in instructions


def test_the_checker_cannot_write_a_verdict() -> None:
    offered = VerificationDigest.model_json_schema(mode="validation")["properties"]

    assert {"success", "disposition", "reason", "failureCause", "gaps"} & set(
        offered
    ) == set()
