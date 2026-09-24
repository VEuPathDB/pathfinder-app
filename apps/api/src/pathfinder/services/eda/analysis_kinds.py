"""Which plugin reads each step's analysis document, read from the site's catalog.

The query a search runs decides it, so a step is read once, when it enters a
graph without a kind; the kind then travels with the stored strategy.
"""

from __future__ import annotations

from collections.abc import Iterable

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import (
    EdaBackedSearch,
    eda_backed_search,
    read_search_definition,
    resolve_search_record_type,
)

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.ast_diff import nodes_of
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda.export import study_step_request

logger = get_logger(__name__)

__all__ = [
    "analysis_kinds_of",
    "kind_of_search",
    "read_the_unread_kinds",
    "unread_analyses",
]


def kind_of_search(described: EdaBackedSearch | None) -> AnalysisKind:
    """The kind of a search, from what the catalog says its query does."""
    if described is None or not described.reads_the_spec:
        return AnalysisKind.NONE
    return AnalysisKind.COMPUTE if described.is_compute_backed else AnalysisKind.SUBSET


async def analysis_kinds_of(
    *, site_id: str, record_type: str | None, nodes: Iterable[StrategyStepNode]
) -> dict[str, StampedKind]:
    """The kind of every step that carries an analysis document, by step id.

    A step that carries none takes no kind, and so does one whose search the
    catalog cannot read; it is read again when it next enters a graph.
    """
    by_search: dict[str, AnalysisKind | None] = {}
    kinds: dict[str, StampedKind] = {}
    for node in nodes:
        if study_step_request(node.parameters) is None:
            continue
        if node.search_name not in by_search:
            by_search[node.search_name] = await _kind_on_the_site(
                site_id, record_type, node.search_name
            )
        kind = by_search[node.search_name]
        if kind is not None:
            kinds[node.id] = StampedKind(search_name=node.search_name, kind=kind)
    return kinds


async def read_the_unread_kinds(*, site_id: str, graph: StrategyGraph) -> None:
    """Give each step of the graph that carries an analysis document its kind.

    A step has none when it entered the graph with none, or when its search
    changed since its kind was read. A search whose catalog read fails is not
    asked again for the rest of the turn, and the next turn reads it again.
    """
    live = graph.to_strategy_ast()
    if live is None:
        return
    unread = [
        node
        for step_id, node in nodes_of(live).items()
        if graph.analysis_kind_of(step_id) is None
        and node.search_name not in graph.unreadable_searches
        and study_step_request(node.parameters) is not None
    ]
    kinds = await analysis_kinds_of(
        site_id=site_id, record_type=graph.record_type, nodes=unread
    )
    graph.note_analysis_kinds(kinds)
    graph.unreadable_searches |= {
        node.search_name for node in unread if node.id not in kinds
    }


def unread_analyses(graph: StrategyGraph) -> list[str]:
    """The steps that carry an analysis document the site has not described.

    Their plugin is unknown, so no check of their cut can run.
    """
    return [
        step_id
        for step_id, step in graph.steps.items()
        if study_step_request(step.parameters) is not None
        and graph.analysis_kind_of(step_id) is None
    ]


async def _kind_on_the_site(
    site_id: str, record_type: str | None, search_name: str
) -> AnalysisKind | None:
    try:
        listed_under = await resolve_search_record_type(
            site_id, search_name, record_type
        )
        definition = await read_search_definition(site_id, listed_under, search_name)
    # The catalog's own loader names these three as the ways a load fails.
    except (VEuPathDBError, OSError, RuntimeError) as exc:
        logger.warning(
            "search definition unreadable",
            site_id=site_id,
            search_name=search_name,
            error=str(exc),
        )
        return None
    return kind_of_search(eda_backed_search(definition))
