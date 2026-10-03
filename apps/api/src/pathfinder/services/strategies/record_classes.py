"""The record classes a site declares for the searches a tree runs."""

from __future__ import annotations

from collections.abc import Collection

from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    get_raw_record_types,
    get_raw_searches,
    make_record_type_resolver,
)

from pathfinder.domain.strategy.validate import SearchRecordClasses


def record_classes_of(search: WDKSearch, listed_under: str) -> SearchRecordClasses:
    """What the search returns and what its input step may hold."""
    return SearchRecordClasses(
        display_name=search.display_name,
        returns=search.output_record_class_name or listed_under,
        takes=tuple(search.allowed_primary_input_record_class_names or ()),
    )


async def search_record_types(
    site_id: str, search_names: Collection[str]
) -> dict[str, str]:
    """The record type the catalog lists each named search under. A search the
    catalog does not list is left out."""
    listed_under = await make_record_type_resolver(site_id)
    found: dict[str, str] = {}
    for name in sorted(set(search_names)):
        record_type = await listed_under(name)
        if record_type is not None:
            found[name] = record_type
    return found


async def search_record_classes(
    site_id: str, search_names: Collection[str]
) -> dict[str, SearchRecordClasses]:
    """The declared record classes of each named search the catalog lists."""
    found: dict[str, SearchRecordClasses] = {}
    for name, record_type in (await search_record_types(site_id, search_names)).items():
        listed = await get_raw_searches(site_id, record_type)
        search = next((s for s in listed if s.url_segment == name), None)
        if search is not None:
            found[name] = record_classes_of(search, record_type)
    return found


async def catalog_search_names(site_id: str) -> list[str]:
    """Every search name the site's catalog lists, under any record type."""
    return [
        search.url_segment
        for record in await get_raw_record_types(site_id)
        for search in await get_raw_searches(site_id, record.url_segment)
    ]


async def record_class_names(site_id: str) -> dict[str, str]:
    """The plural display name of each record class the site publishes."""
    return {
        record.url_segment: record.display_name_plural or record.url_segment
        for record in await get_raw_record_types(site_id)
    }
