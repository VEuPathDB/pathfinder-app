"""The coaching this product supplies reaches the index and the promote tool.

An empty guidance is a complete index and a generic tool description, so the
strings are pinned where the model reads them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from assistant_core.scratchpad.models import Note
from assistant_core.scratchpad.rendering import render_scratchpad
from assistant_core.scratchpad.toolset import build_scratchpad_toolset
from pydantic_ai import Agent
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.scratchpad_guidance import (
    PATHFINDER_SCRATCHPAD_GUIDANCE,
    PROMOTED_NOTE_KIND,
)
from pathfinder.ai.agents.verification import build_verification_agent

_PROMOTE_SENTENCE = (
    "Use when a note captures reusable biological knowledge that is worth "
    "remembering beyond this conversation: a mechanism, a named marker "
    "set, a fact about an organism."
)

_INSTANT = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

_NOTE = Note(
    id="n_1",
    conversation_id=UUID(int=1),
    title="GO:0004672 reaches 105 kinases",
    summary="the kinase criterion",
    body="body",
    tags=[],
    pinned=False,
    body_tokens=1,
    created_at=_INSTANT,
    updated_at=_INSTANT,
)


def _unwrap(toolset: AbstractToolset[Any]) -> AbstractToolset[Any]:
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
    return toolset


def _promote_description(toolset: AbstractToolset[Any]) -> str:
    described = _describe_promote(toolset)
    assert described is not None
    return described


def _describe_promote(toolset: AbstractToolset[Any]) -> str | None:
    """The promote tool's description, or None when this toolset has no promote."""
    inner = _unwrap(toolset)
    if not isinstance(inner, FunctionToolset):
        return None
    tool = inner.tools.get("promote_to_memory")
    return None if tool is None else tool.description or ""


def _promote_with_guidance() -> str:
    return _promote_description(
        build_scratchpad_toolset(
            guidance=PATHFINDER_SCRATCHPAD_GUIDANCE, promoted_kind=PROMOTED_NOTE_KIND
        ),
    )


def test_the_empty_index_carries_this_products_coaching() -> None:
    """The whole block, so the runtime's line break stays pinned here."""
    rendered = render_scratchpad(
        [],
        total_count=0,
        guidance=PATHFINDER_SCRATCHPAD_GUIDANCE,
    )

    assert rendered == (
        "## Notes (empty)\n"
        "\n"
        "No notes yet.\n"
        "\n"
        "As you work, call note(...) to save:\n"
        "  - interesting searches and their params\n"
        "  - dead ends (so you don't retry them)\n"
        "  - assumptions about the user's intent\n"
        "  - decisions and why you made them\n"
        "\n"
        "Rule: Before moving on from any promising search or parameter trial, "
        "call note(...)."
    )


def test_a_populated_index_ends_with_the_rule_this_product_states() -> None:
    rendered = render_scratchpad(
        [_NOTE],
        total_count=1,
        guidance=PATHFINDER_SCRATCHPAD_GUIDANCE,
    )

    assert rendered == (
        "## Notes (1 notes, 0 pinned)\n"
        "### Recent\n"
        "  [n_1] GO:0004672 reaches 105 kinases\n"
        "             the kinase criterion\n"
        "\n"
        "Rule: Before moving on from any promising search or parameter trial, "
        "call note(...).\n"
        "      Before ending your turn, review notes (list_notes/search_notes) "
        "and pin_note(...) load-bearing findings.\n"
        "      In your typed delta, reference supporting notes via note_refs "
        "when possible."
    )


def test_the_promote_tool_reads_this_products_sentence() -> None:
    """Without it the model reads the runtime's generic description."""
    with_guidance = build_scratchpad_toolset(
        guidance=PATHFINDER_SCRATCHPAD_GUIDANCE, promoted_kind=PROMOTED_NOTE_KIND
    )
    without = build_scratchpad_toolset(promoted_kind=PROMOTED_NOTE_KIND)

    assert _promote_description(with_guidance).endswith(_PROMOTE_SENTENCE)
    assert _PROMOTE_SENTENCE not in _promote_description(without)


@pytest.mark.parametrize(
    "build",
    [build_frame_agent, build_execution_agent, build_verification_agent],
    ids=["frame", "execution", "verification"],
)
def test_a_sub_agent_builds_its_toolset_under_this_guidance(
    build: Callable[[], Agent[Any, Any]],
) -> None:
    """The agents pass the guidance, so the sentence reaches the live tool."""
    descriptions = [
        _describe_promote(toolset)
        for toolset in build().toolsets
        if _describe_promote(toolset) is not None
    ]

    assert descriptions == [_promote_with_guidance()]
