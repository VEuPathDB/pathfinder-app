"""The steps an arc grows the strategy by: an orthology transform, the round trip
back to the site organism, an added search, or orthologs only the portal runs.

A growth applies to a fresh seed and to the tree an EDIT work order prints alike.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import (
    CriterionSpec,
    SpecPlan,
    combine,
    leaf,
    transform,
)
from pathfinder.ai.models.mock.strategy_specs import (
    ORTHOLOGS,
    TAXON,
    intersect_spec,
    seed_criterion,
)
from pathfinder.domain.strategy.operational_spec import StructureNode

# The searches an added step runs, the first one the site's seeds carry, and
# the words a request names each by.
_ADDED_SEARCHES = {
    "GenesByExportPrediction": "exported",
    "GenesByMolecularWeight": "molecular weight",
}
ORTHOLOGS_WORDS = "orthologs"
SYNTENIC_WORDS = "syntenic orthologs"
KEPT_WORDS = "those with syntenic orthologs"


@dataclass(frozen=True)
class Growth:
    """The criteria a growth binds, and the tree it makes of the one it grows."""

    criteria: tuple[CriterionSpec, ...]
    grow: Callable[[StructureNode], StructureNode]


def applied(seed: SpecPlan, growth: Growth, title: str) -> SpecPlan:
    return SpecPlan(
        title=title,
        criteria=(*seed.criteria, *growth.criteria),
        structure=growth.grow(seed.structure),
    )


def orthologs_criterion(
    values: SiteValues, criterion_id: str, *, syntenic: str, back: bool = False
) -> CriterionSpec:
    """Orthologs in a second organism of the sheet, or back in the site organism."""
    words = SYNTENIC_WORDS if syntenic == "yes" else ORTHOLOGS_WORDS
    if back:
        return CriterionSpec(
            criterion_id=criterion_id,
            text=KEPT_WORDS,
            search_name=ORTHOLOGS,
            role="transform",
            values={"organism": [values.organism], "isSyntenic": syntenic},
        )
    return CriterionSpec(
        criterion_id=criterion_id,
        text=words,
        search_name=ORTHOLOGS,
        role="transform",
        values={"isSyntenic": syntenic},
        alt_param="organism",
        site_organism=values.organism,
        alt_same_genus=not values.is_portal,
    )


def orthologs_growth(values: SiteValues, *, syntenic: str) -> Growth:
    there = orthologs_criterion(values, "orthologs", syntenic=syntenic)
    return Growth(criteria=(there,), grow=lambda tree: transform(there, tree))


def round_trip_growth(values: SiteValues) -> Growth:
    """The tree INTERSECT its syntenic orthologs elsewhere, mapped back."""
    there = orthologs_criterion(values, "orthologs_there", syntenic="yes")
    back = orthologs_criterion(values, "orthologs_back", syntenic="yes", back=True)

    def grow(tree: StructureNode) -> StructureNode:
        copied = StructureNode(kind="copy", inputs=[tree])
        trip = transform(back, transform(there, copied))
        return combine(CombineOp.INTERSECT, tree, trip)

    return Growth(criteria=(there, back), grow=grow)


def added_growth(values: SiteValues, held: Collection[str]) -> Growth:
    """One more search, the first listed one the strategy does not run, called
    by its own words, under a new INTERSECT with the whole tree. A site that
    carries none adds its organism."""
    search = next(
        (s for s in _ADDED_SEARCHES if values.leaf(s) is not None and s not in held),
        TAXON,
    )
    words = _ADDED_SEARCHES.get(search, values.organism)
    added = seed_criterion(values, search, "added_step", words)
    return Growth(
        criteria=(added,),
        grow=lambda tree: combine(CombineOp.INTERSECT, tree, leaf(added)),
    )


def portal_only_criterion(values: SiteValues) -> CriterionSpec:
    """Orthologs in an organism the portal holds and the site's transform does
    not reach, which only the portal runs."""
    return CriterionSpec(
        criterion_id="orthologs_elsewhere",
        text="orthologs in an organism of another site",
        search_name=ORTHOLOGS,
        role="transform",
        values={"isSyntenic": "no"},
        outside_param="organism",
        outside_choices=values.portal_organisms,
    )


def orthologs_spec(values: SiteValues) -> SpecPlan:
    return applied(
        intersect_spec(values),
        orthologs_growth(values, syntenic="no"),
        f"orthologs of {values.organism} secreted membrane genes (mock)",
    )


def syntenic_orthologs_spec(values: SiteValues) -> SpecPlan:
    return applied(
        intersect_spec(values),
        orthologs_growth(values, syntenic="yes"),
        f"syntenic orthologs of {values.organism} secreted membrane genes (mock)",
    )


def round_trip_spec(values: SiteValues) -> SpecPlan:
    return applied(
        intersect_spec(values),
        round_trip_growth(values),
        f"{values.organism} genes with a syntenic ortholog elsewhere (mock)",
    )
