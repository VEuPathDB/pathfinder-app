"""Every agent runs the runtime's history processors, in the runtime's order."""

from __future__ import annotations

from collections.abc import Callable
from typing import Never

import pytest
from assistant_core.conversation.history import HISTORY_PROCESSORS
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.lead.lead_agent import build_lead_agent

_BUILDERS: tuple[Callable[[], Agent[Never, object]], ...] = (
    build_frame_agent,
    build_execution_agent,
    build_verification_agent,
    build_lead_agent,
)


def _processors(agent: Agent[Never, object]) -> tuple[object, ...]:
    return tuple(
        capability.processor
        for capability in agent.root_capability.capabilities
        if isinstance(capability, ProcessHistory)
    )


@pytest.mark.parametrize("builder", _BUILDERS, ids=lambda b: b.__name__)
def test_agent_runs_the_runtime_processors(
    builder: Callable[[], Agent[Never, object]],
) -> None:
    assert _processors(builder()) == HISTORY_PROCESSORS


def test_the_runtime_order_is_pairing_then_elision_then_compaction() -> None:
    assert [fn.__name__ for fn in HISTORY_PROCESSORS] == [
        "pair_orphans",
        "elide_consumed",
        "compact_history",
    ]
