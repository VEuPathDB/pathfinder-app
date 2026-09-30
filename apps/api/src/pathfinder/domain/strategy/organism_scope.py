"""The organism a bound criterion runs on, read from the parameter its search
marks as the organism."""

from __future__ import annotations

from collections.abc import Collection, Iterable

from veupathdb.domain.strategy import StrategyStepNode, extract_output_organisms

from pathfinder.domain.strategy.operational_spec import Criterion


def organism_params_of(criteria: Iterable[Criterion]) -> dict[str, str]:
    """Each bound search of the criteria, and the parameter it marks as the organism."""
    return {
        c.search_name: c.organism_param
        for c in criteria
        if c.search_name and c.organism_param is not None
    }


def selected_organisms(criterion: Criterion) -> frozenset[str]:
    """The values the criterion selects on its organism parameter."""
    if criterion.organism_param is None:
        return frozenset()
    step = StrategyStepNode(
        search_name=criterion.search_name, parameters=criterion.param_values
    )
    found = extract_output_organisms(
        step, {criterion.search_name: criterion.organism_param}
    )
    return frozenset(found or ())


def organism_only(criterion: Criterion, organisms: Collection[str]) -> bool:
    """Whether the organism is the one value the criterion states.

    Every other parameter holds its default, and every value the organism
    parameter selects is an organism of the site: a marked vocabulary can list
    other terms under its organism branches.
    """
    selected = selected_organisms(criterion)
    others = set(criterion.resolved_params) - {criterion.organism_param}
    return (
        bool(selected)
        and others <= set(criterion.defaulted())
        and selected <= set(organisms)
    )


def universe_key(
    criterion: Criterion, organisms: Collection[str]
) -> tuple[str, ...] | None:
    """The sorted organisms whose gene count decides whether the criterion narrows.

    None when the binding states more than the organism or has no count, since
    then no count identity can make it redundant.
    """
    if criterion.result_count is None or not organism_only(criterion, organisms):
        return None
    return tuple(sorted(selected_organisms(criterion)))
