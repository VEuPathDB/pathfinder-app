"""The refusals every phase agent reads with its system prompt."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic_ai import Agent

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.strategy_instructions import base_system_prompt
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.tests._support.instructions import pinned_instructions

# The two refusals that belong to the agents holding the write tools. What the
# Lead may write about is a classification, not a refusal, and lives with
# ``classify_user_intent``.
CODE_REFUSAL = "Execute arbitrary code or shell commands"
UNRELATED_REFUSAL = "Generate content unrelated to bioinformatics research"

_BUILDERS: list[Callable[[], Agent[Any, Any]]] = [
    build_frame_agent,
    build_execution_agent,
    build_verification_agent,
]


def _refusals(prompt: str) -> list[str]:
    """The numbered refusals the pinned prompt lists, in order."""
    listed = prompt.split("You should REFUSE to:")[1].split("\n\n", maxsplit=1)[0]
    return [line.split(". ", 1)[1] for line in listed.strip().splitlines()]


def test_the_pinned_system_prompt_lists_every_refusal() -> None:
    assert _refusals(base_system_prompt(MagicMock())) == [
        CODE_REFUSAL,
        "Access external URLs not related to VEuPathDB",
        "Provide medical advice or clinical recommendations",
        UNRELATED_REFUSAL,
    ]


@pytest.mark.parametrize("build_agent", _BUILDERS)
def test_every_phase_agent_pins_the_prompt_that_carries_them(
    build_agent: Callable[[], Agent[Any, Any]],
) -> None:
    assert "base_system_prompt" in pinned_instructions(build_agent())
