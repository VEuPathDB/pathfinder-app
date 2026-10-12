"""Whether an INTERSECT of the tree FRAME states can meet, read against the
site's organism tree when two scopes differ by name."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.organism_scope import (
    dataset_organisms_of,
    organism_params_of,
)
from pathfinder.domain.strategy.validate import first_cross_organism_refusal
from pathfinder.services.strategies.organism_params import organism_taxa


async def stated_cross_organism_refusal(
    site_id: str, stated: OperationalSpec, steps: StrategyStepNode
) -> str | None:
    """Why the first INTERSECT of the stated tree can never meet, or None."""
    marks = organism_params_of(stated.criteria)
    datasets = dataset_organisms_of(stated.criteria)
    if first_cross_organism_refusal(steps, marks, datasets) is None:
        return None
    taxa = await organism_taxa(site_id, stated.record_type, marks)
    return first_cross_organism_refusal(steps, marks, datasets, taxa=taxa)
