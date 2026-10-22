"""The parameter each search of a site marks as its organism, and the organisms of
the dataset a step runs on, read from the catalog."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, walk
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import (
    EDA_DATASET_ID_PARAM,
    dataset_organisms,
    organism_parameter,
    read_search_definition,
    study_organisms,
)

from pathfinder.domain.strategy.named_taxa import organism_trees
from pathfinder.domain.strategy.validate import first_cross_organism_refusal
from pathfinder.services.strategies.record_classes import search_record_types

logger = get_logger(__name__)


async def organism_parameters(
    site_id: str, search_names: Collection[str]
) -> dict[str, str]:
    """Each search the catalog reads that marks an organism parameter, and its name,
    each read under the record type the catalog lists it under.

    A search the catalog does not list, or cannot read, names none, so a check
    that reads the map abstains on it.
    """
    marks: dict[str, str] = {}
    listed = await search_record_types(site_id, search_names)
    for search_name, listed_under in sorted(listed.items()):
        try:
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


async def step_dataset_organisms(
    site_id: str, search_name: str, parameters: Mapping[str, ParamValue]
) -> list[str]:
    """The organisms of the dataset a step runs on: its study's when a parameter
    names one, else those of the one dataset that names its search."""
    match parameters.get(EDA_DATASET_ID_PARAM):
        case StringValue(value=study) if study:
            return await study_organisms(site_id, study)
        case _:
            return await dataset_organisms(site_id, search_name)


def _reads_an_organism(nodes: list[StrategyStepNode]) -> bool:
    """Only an INTERSECT or a transform reads an organism."""
    return any(
        node.operator is CombineOp.INTERSECT or node.infer_kind() == "transform"
        for node in nodes
    )


async def tree_dataset_organisms(
    site_id: str, root: StrategyStepNode, organism_params: Mapping[str, str]
) -> dict[str, frozenset[str]]:
    """The organisms of the dataset each step of a tree runs on, by step id, for
    the steps whose search marks no organism parameter. A tree that reads no
    organism reads nothing."""
    nodes = walk(root)
    if not _reads_an_organism(nodes):
        return {}
    found: dict[str, frozenset[str]] = {}
    for node in nodes:
        if node.infer_kind() == "combine" or node.search_name in organism_params:
            continue
        organisms = await step_dataset_organisms(
            site_id, node.search_name, node.parameters
        )
        if organisms:
            found[node.id] = frozenset(organisms)
    return found


async def tree_organism_parameters(
    site_id: str, root: StrategyStepNode
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
        [node.search_name for node in nodes if node.infer_kind() != "combine"],
    )


async def organism_taxa(
    site_id: str, organism_params: Mapping[str, str]
) -> dict[str, frozenset[str]]:
    """The organisms under each entry of the organism tree of every marked search.

    A search the catalog does not list, or cannot read, gives none, so its entries
    stand for themselves.
    """
    taxa: dict[str, frozenset[str]] = {}
    listed = await search_record_types(site_id, organism_params)
    for search_name, listed_under in sorted(listed.items()):
        try:
            definition = await read_search_definition(
                site_id, listed_under, search_name
            )
        except (VEuPathDBError, OSError) as exc:
            logger.warning(
                "organism tree unreadable", search_name=search_name, error=str(exc)
            )
            continue
        tree = organism_trees(definition).get(organism_params[search_name])
        if tree is not None:
            taxa.update(tree.parents)
    return taxa


async def tree_cross_organism_refusal(
    site_id: str, root: StrategyStepNode
) -> str | None:
    """Why the first INTERSECT of the tree can never meet, or None when each one
    can or a scope is unknown. The organism tree is read only when two scopes
    differ by name."""
    marks = await tree_organism_parameters(site_id, root)
    datasets = await tree_dataset_organisms(site_id, root, marks)
    taxa = await tree_taxa(site_id, root, marks, datasets)
    return first_cross_organism_refusal(root, marks, datasets, taxa=taxa)


async def tree_taxa(
    site_id: str,
    root: StrategyStepNode,
    organism_params: Mapping[str, str],
    dataset_organisms: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """The organisms under each entry of the organism trees a tree reads, or none
    when no INTERSECT of the tree joins two scopes that differ by name."""
    if first_cross_organism_refusal(root, organism_params, dataset_organisms) is None:
        return {}
    return await organism_taxa(site_id, organism_params)
