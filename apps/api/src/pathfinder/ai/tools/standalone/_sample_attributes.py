"""The record attributes a check's sample of the root is read with."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Sequence

from veupathdb.domain.strategy import StepKind
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import get_raw_record_types, get_raw_searches
from veupathdb_mcp.tool_payloads import gene_sample_attributes

from pathfinder.domain.strategy.session import StrategyGraph

# An attribute a fifth or more of the record type's searches show by default,
# such as the organism, says nothing about what one search selects.
_COMMON_SHARE = 5
_MOST_ATTRIBUTES = 12


def selecting_attributes(
    searches: Sequence[WDKSearch],
    record_attributes: Collection[str],
    search_names: Iterable[str],
) -> list[str]:
    """The record attributes the named searches show by default and few others show."""
    shown = Counter(
        name for search in searches for name in set(search.default_attributes)
    )
    by_name = {search.url_segment: search for search in searches}
    found = dict.fromkeys(
        name
        for search_name in search_names
        if (search := by_name.get(search_name)) is not None
        for name in search.default_attributes
        if name in record_attributes and shown[name] * _COMMON_SHARE < len(searches)
    )
    return list(found)[:_MOST_ATTRIBUTES]


def _leaf_search_names(graph: StrategyGraph) -> list[str]:
    return [
        step.search_name
        for step in graph.steps.values()
        if step.kind is not StepKind.COMBINE and step.search_name
    ]


async def _own_columns(
    site_id: str, record_type: str, search_name: str | None
) -> list[str]:
    """The columns a step's own search shows: every default for a record type
    with no gene columns, else the columns it adds that few other searches show."""
    if search_name is None:
        return []
    searches = await get_raw_searches(site_id, record_type)
    search = next((s for s in searches if s.url_segment == search_name), None)
    if search is None:
        return []
    if gene_sample_attributes(record_type) is None:
        return [n for n in search.default_attributes if n != "primary_key"]
    added = {field.name for field in search.dynamic_attributes}
    return selecting_attributes(searches, added, [search_name])


async def _selected(
    site_id: str, record_type: str, graph: StrategyGraph | None
) -> list[str]:
    if graph is None:
        return []
    record = next(
        (
            rt
            for rt in await get_raw_record_types(site_id)
            if rt.url_segment == record_type
        ),
        None,
    )
    if record is None:
        return []
    fields = record.attributes or list((record.attributes_map or {}).values())
    return selecting_attributes(
        await get_raw_searches(site_id, record_type),
        {field.name for field in fields},
        _leaf_search_names(graph),
    )


async def sample_attributes(
    site_id: str,
    record_type: str,
    graph: StrategyGraph | None,
    *,
    own_search: str | None,
) -> list[str]:
    """The attributes the graph's searches select on, then the columns the
    sampled step's own search shows, as the site's catalog lists them."""
    return [
        *await _selected(site_id, record_type, graph),
        *await _own_columns(site_id, record_type, own_search),
    ]
