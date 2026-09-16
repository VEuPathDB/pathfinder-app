from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from assistant_core.scratchpad.toolset import build_scratchpad_toolset
from pydantic_ai import Agent
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.prepared import PreparedToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.scratchpad_guidance import PROMOTED_NOTE_KIND
from pathfinder.ai.agents.verification import build_verification_agent

_SCRATCHPAD_TOOL_NAMES = (
    "note",
    "list_notes",
    "search_notes",
    "read_note",
    "update_note",
    "delete_note",
    "pin_note",
    "unpin_note",
    "promote_to_memory",
)


def _unwrap(ts: AbstractToolset[Any]) -> AbstractToolset[Any]:
    while isinstance(ts, WrapperToolset):
        ts = ts.wrapped
    return ts


def test_scratchpad_toolset_lists_all_tools() -> None:
    ts = build_scratchpad_toolset(promoted_kind=PROMOTED_NOTE_KIND)
    inner = _unwrap(ts)
    assert isinstance(inner, FunctionToolset)
    names = set(inner.tools.keys())
    for required in _SCRATCHPAD_TOOL_NAMES:
        assert required in names, f"{required} missing from build_scratchpad_toolset"


def test_scratchpad_toolset_is_prepared_for_dynamic_filtering() -> None:
    ts = build_scratchpad_toolset(promoted_kind=PROMOTED_NOTE_KIND)
    assert isinstance(ts, PreparedToolset)


def _caller_toolsets(
    agent: Agent[Any, Any],
) -> list[FunctionToolset[Any]]:
    unwrapped = [_unwrap(ts) for ts in agent.toolsets]
    return [ts for ts in unwrapped if type(ts) is FunctionToolset]


def _flat_tool_names_from_agent(agent: Agent[Any, Any]) -> set[str]:
    found: set[str] = set()
    for ts in _caller_toolsets(agent):
        found.update(ts.tools.keys())
    return found


@pytest.mark.parametrize(
    "build",
    [
        build_frame_agent,
        build_execution_agent,
        build_verification_agent,
    ],
    ids=["frame", "execution", "verification"],
)
def test_phase_agent_exposes_scratchpad_tools(
    build: Callable[[], Agent[Any, Any]],
) -> None:
    """Each phase agent composes the scratchpad toolset alongside its phase tools."""
    agent = build()
    names = _flat_tool_names_from_agent(agent)
    for required in _SCRATCHPAD_TOOL_NAMES:
        assert required in names, (
            f"{required} missing from {agent.name!r} agent toolsets"
        )


@pytest.mark.parametrize(
    "build",
    [
        build_frame_agent,
        build_execution_agent,
        build_verification_agent,
    ],
    ids=["frame", "execution", "verification"],
)
def test_phase_toolset_does_not_embed_scratchpad(
    build: Callable[[], Agent[Any, Any]],
) -> None:
    """Scratchpad tools come from the scratchpad toolset only - not duplicated
    into the phase toolset. Guards against DRY-violating re-imports.
    """
    agent = build()
    phase_toolsets = _caller_toolsets(agent)
    # There must be exactly 2 caller-provided toolsets: the phase-specific
    # one and the scratchpad one. The scratchpad one owns every scratchpad
    # tool.
    assert len(phase_toolsets) == 2, (
        f"{agent.name!r} has {len(phase_toolsets)} caller FunctionToolsets; expected 2"
    )
    owners: dict[str, int] = dict.fromkeys(_SCRATCHPAD_TOOL_NAMES, 0)
    for ts in phase_toolsets:
        for name in ts.tools:
            if name in owners:
                owners[name] += 1
    for name, count in owners.items():
        assert count == 1, (
            f"{name} is defined {count} times across {agent.name!r}'s toolsets; "
            f"expected exactly 1 (scratchpad-only)"
        )
