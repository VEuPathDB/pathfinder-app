from __future__ import annotations

from veupathdb.domain.parameters import PhyleticTree
from veupathdb_mcp.catalog import phyletic_tree_for_search, read_search_definition

from strategist.domain.strategy.genome_set_names import (
    searches_with_unnamed_genomes,
    spec_with_named_genomes,
)
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.services.strategies.record_classes import search_record_types


async def _trees(
    site_id: str, search_names: set[str]
) -> dict[str, PhyleticTree | None]:
    listed = await search_record_types(site_id, sorted(search_names))
    trees: dict[str, PhyleticTree | None] = {}
    for search_name, record_type in listed.items():
        definition = await read_search_definition(site_id, record_type, search_name)
        trees[search_name] = await phyletic_tree_for_search(site_id, definition)
    return trees


async def spec_with_its_genomes_named(
    spec: OperationalSpec | None, *, site_id: str
) -> OperationalSpec | None:
    searches = searches_with_unnamed_genomes(spec)
    if spec is None or not searches:
        return spec
    return spec_with_named_genomes(spec, await _trees(site_id, searches))


__all__ = ["spec_with_its_genomes_named"]
