"""Phase-role registry: the model each role runs on when the user pins nothing."""

from __future__ import annotations

from pathfinder.ai.agents.execution import EXECUTION_MODEL
from pathfinder.ai.agents.frame import FRAME_MODEL
from pathfinder.ai.agents.verification import VERIFICATION_MODEL
from pathfinder.ai.explore.explore_agent import EXPLORE_MODEL
from pathfinder.ai.lead.lead_agent import LEAD_MODEL

__all__ = ["phase_defaults"]


def phase_defaults() -> dict[str, str]:
    """The compile-time model of every role the product declares.

    Every agent is built per run, so each default is the model its factory
    bakes in rather than a model read off a live agent.
    """
    return {
        "lead": LEAD_MODEL,
        "frame": FRAME_MODEL,
        "execution": EXECUTION_MODEL,
        "verification": VERIFICATION_MODEL,
        "explore": EXPLORE_MODEL,
    }
