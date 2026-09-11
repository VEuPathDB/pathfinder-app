"""The search listing a FRAME run reads stays inside its history budget.

The portal is the largest catalog, so its transcript listing is the pin: a
listing over the compaction threshold rewrites the FRAME history on every step.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from assistant_core.conversation.history import compact_history
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    UserPromptPart,
)
from veupathdb_mcp import tool_payloads

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.catalog import list_searches
from pathfinder.tests._support.tool_exchange import tool_exchange
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

# The transcript listing of veupathdb.org, read from the site: 2769 searches,
# 189916 characters of name and 293176 of display name.
PORTAL_SEARCHES = 2769
PORTAL_NAME_CHARS = 189_916
PORTAL_DISPLAY_NAME_CHARS = 293_176

_WORK_ORDER = "FRAME work order: bind the seed criterion"


def _text_of_length(index: int, total_chars: int) -> str:
    width, extra = divmod(total_chars, PORTAL_SEARCHES)
    return f"{index:0{width + (1 if index < extra else 0)}d}"


def _portal_rows() -> list[tool_payloads.SearchListing]:
    """Rows at the portal listing's count and text length."""
    return [
        tool_payloads.SearchListing(
            name=_text_of_length(index, PORTAL_NAME_CHARS),
            display_name=_text_of_length(index, PORTAL_DISPLAY_NAME_CHARS),
        )
        for index in range(PORTAL_SEARCHES)
    ]


def _ctx() -> RunContext[AgentDeps]:
    return agent_run_context(site_id="veupathdb", tool_call_id="call_listing")


def _frame_history(listing: object) -> list[ModelMessage]:
    """A FRAME run that reads the listing, then reads a sheet and binds it."""
    return [
        ModelRequest(parts=[UserPromptPart(content=_WORK_ORDER)]),
        *tool_exchange(1, "list_searches", listing),
        *tool_exchange(
            2,
            "set_criterion",
            {"criterionId": "taxon_genes", "paramsTemplate": {"organism": None}},
        ),
        *tool_exchange(
            3,
            "set_criterion",
            {
                "criterionId": "taxon_genes",
                "resolvedParams": {"organism": ["Plasmodium falciparum 3D7"]},
            },
        ),
    ]


def test_the_rows_carry_the_measured_portal_text() -> None:
    rows = _portal_rows()

    assert len(rows) == PORTAL_SEARCHES
    assert sum(len(row.name) for row in rows) == PORTAL_NAME_CHARS
    assert sum(len(row.display_name) for row in rows) == PORTAL_DISPLAY_NAME_CHARS


async def test_the_portal_listing_leaves_the_frame_history_uncompacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tool_payloads, "list_search_listings", AsyncMock(return_value=_portal_rows())
    )

    listing = returned(await list_searches(_ctx()), list[str])
    history = _frame_history(listing)

    assert len(listing) == PORTAL_SEARCHES
    assert compact_history(history) == history


def test_a_listing_that_carries_the_display_name_is_compacted() -> None:
    labelled = [row.model_dump(by_alias=True) for row in _portal_rows()]

    history = _frame_history(labelled)

    assert compact_history(history) != history
