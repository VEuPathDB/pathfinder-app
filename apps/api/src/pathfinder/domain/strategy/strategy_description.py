import re

from veupathdb.domain.strategy import StrategyStep

from pathfinder.domain.strategy.computed_groups import SNAPSHOT_NOTE
from pathfinder.domain.strategy.session import StrategyGraph

_DERIVED = re.compile(r"(Find|Transform|Combine) (\S+ )?results for .+\.")


def derived_description(record_type: str | None, root_step: StrategyStep) -> str:
    kind = root_step.kind.value
    if kind == "search":
        summary = root_step.display_name or root_step.search_name
        verb = "Find"
    elif kind == "transform":
        summary = root_step.display_name or root_step.search_name
        verb = "Transform"
    else:
        operator = root_step.operator.value.lower() if root_step.operator else None
        summary = root_step.display_name or operator or "combine"
        verb = "Combine"
    summary = (summary or "").strip()
    if not summary:
        summary = "results"
    if record_type:
        return f"{verb} {record_type} results for {summary}."
    return f"{verb} results for {summary}."


def strategy_description(graph: StrategyGraph, root_id: str) -> str:
    if graph.description:
        return graph.description
    return derived_description(graph.record_type, graph.steps[root_id])


def shown_description(graph: StrategyGraph) -> str | None:
    root_id = graph.primary_root_id()
    if root_id is None:
        return graph.description
    return strategy_description(graph, root_id)


def stated_description(stored: str | None) -> str | None:
    if not stored:
        return None
    head = stored.removesuffix(f" {SNAPSHOT_NOTE}")
    if not _DERIVED.fullmatch(head):
        return stored
    return SNAPSHOT_NOTE if head != stored else None
