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
    resolve_search_record_type,
    study_organisms,
)

from pathfinder.domain.strategy.validate import first_cross_organism_refusal

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


async def tree_cross_organism_refusal(
    site_id: str, record_type: str | None, root: StrategyStepNode
) -> str | None:
    """Why the first INTERSECT of the tree can never meet, or None when each one
    can or a scope is unknown."""
    marks = await tree_organism_parameters(site_id, record_type, root)
    datasets = await tree_dataset_organisms(site_id, root, marks)
    return first_cross_organism_refusal(root, marks, datasets)
