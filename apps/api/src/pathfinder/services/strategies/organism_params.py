"""The parameter each search of a site marks as its organism, read from the catalog."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, walk
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import (
    dataset_organisms,
    organism_parameter,
    resolve_search_record_type,
)

logger = get_logger(__name__)


async def organism_parameters(
    site_id: str, record_type: str | None, search_names: Collection[str]
) -> dict[str, str]:
    """Each search the catalog reads that marks an organism parameter, and its name.

    A search the catalog cannot read names none, so a check that reads the map
    abstains on it.
    """
    marks: dict[str, str] = {}
    for search_name in sorted(set(search_names)):
        try:
            listed_under = await resolve_search_record_type(
                site_id, search_name, record_type
            )
            marked = await organism_parameter(site_id, listed_under, search_name)
        except (VEuPathDBError, OSError) as exc:
            logger.warning(
                "organism parameter unreadable",
                search_name=search_name,
                error=str(exc),
            )
            continue
        if marked is not None:
            marks[search_name] = marked
    return marks


def _reads_an_organism(nodes: list[StrategyStepNode]) -> bool:
    """Only an INTERSECT or a transform reads an organism."""
    return any(
        node.operator is CombineOp.INTERSECT or node.infer_kind() == "transform"
        for node in nodes
    )


async def tree_dataset_organisms(
    site_id: str, root: StrategyStepNode, organism_params: Mapping[str, str]
) -> dict[str, frozenset[str]]:
    """The organisms of the dataset each search of a step tree runs on, for the
    searches that mark no organism parameter. A tree that reads no organism
    reads nothing."""
    nodes = walk(root)
    if not _reads_an_organism(nodes):
        return {}
    unmarked = sorted(
        {
            node.search_name
            for node in nodes
            if node.infer_kind() != "combine"
            and node.search_name not in organism_params
        }
    )
    found: dict[str, frozenset[str]] = {}
    for search_name in unmarked:
        organisms = await dataset_organisms(site_id, search_name)
        if organisms:
            found[search_name] = frozenset(organisms)
    return found


async def tree_organism_parameters(
    site_id: str, record_type: str | None, root: StrategyStepNode
) -> dict[str, str]:
    """The organism parameter of every search a step tree runs.

    Only an INTERSECT or a transform reads an organism, so a tree with neither
    reads nothing.
    """
    nodes = walk(root)
    if not _reads_an_organism(nodes):
        return {}
    return await organism_parameters(
        site_id,
        record_type,
        [node.search_name for node in nodes if node.infer_kind() != "combine"],
    )
