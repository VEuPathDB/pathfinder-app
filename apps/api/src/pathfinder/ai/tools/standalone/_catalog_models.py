"""Catalog-related response models and helpers."""

from __future__ import annotations

from assistant_core.platform.types import JSONObject
from veupathdb.wdk.wdk_models import WDKSearch
from veupathdb_mcp.catalog.searches import read_search_definition

from pathfinder.ai.agents.state import AgentToolState, SearchOverview

_UNIVERSAL_SEARCHES: list[JSONObject] = [
    {
        "name": "GenesByText",
        "displayName": "Gene Text Search",
        "description": "Search all text fields for genes matching a keyword or phrase.",
        "category": "general",
        "returns": "transcript",
        "relevanceScore": 0.0,
    },
]


def _search_overview_of(search: WDKSearch, record_type: str) -> SearchOverview:
    """The discovery-gate entry for a search, from its expanded WDK definition."""
    visible = [p for p in search.parameters or [] if p.is_visible]
    return SearchOverview(
        search_name=search.url_segment,
        display_name=search.display_name or search.url_segment,
        record_type=record_type,
        description=search.description or search.summary,
        parameter_names=[p.name for p in visible],
        required_params=[
            p.name
            for p in visible
            if not p.allow_empty_value or p.min_selected_count >= 1
        ],
    )


def register_search(state: AgentToolState, search: WDKSearch, record_type: str) -> None:
    """Register a search in the discovery gate when nothing registered it yet."""
    if state.get_overview(search.url_segment) is not None:
        return
    state.register_search(search.url_segment, _search_overview_of(search, record_type))


async def ensure_search_registered(
    state: AgentToolState, site_id: str, record_type: str, search_name: str
) -> None:
    """Register a search the caller holds no definition for.

    The definition is read only when the discovery gate has no entry yet.
    """
    if state.get_overview(search_name) is not None:
        return
    definition = await read_search_definition(site_id, record_type, search_name)
    register_search(state, definition, record_type)
