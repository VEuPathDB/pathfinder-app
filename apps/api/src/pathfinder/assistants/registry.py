"""The composition root: which assistants this deployment serves."""

from __future__ import annotations

from functools import lru_cache

from assistant_core.registry import AssistantRegistry

from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.site_help.spec import build_site_help_spec
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@lru_cache(maxsize=1)
def get_assistant_registry() -> AssistantRegistry:
    """Every installed assistant. Built once; the specs hold no per-turn state."""
    return AssistantRegistry(
        specs=[build_pathfinder_spec(), build_site_help_spec()],
        default_id=PATHFINDER_ASSISTANT_ID,
    )


__all__ = ["get_assistant_registry"]
