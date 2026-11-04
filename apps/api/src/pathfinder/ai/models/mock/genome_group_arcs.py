from __future__ import annotations

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionSpec, SpecPlan, leaf

ORTHOLOG_PATTERN = "GenesByOrthologPattern"


def ortholog_in_a_group_spec(values: SiteValues) -> SpecPlan:
    profile = CriterionSpec(
        criterion_id="ortholog_in_a_group",
        text="genes with an ortholog in the listed genomes",
        search_name=ORTHOLOG_PATTERN,
        values={
            "organism": [values.organism],
            "included_species": ["pber", "pfal"],
            "excluded_species": ["hsap"],
        },
    )
    return SpecPlan(
        title=f"{values.organism} genes with an ortholog in the listed genomes",
        criteria=(profile,),
        structure=leaf(profile),
    )


__all__ = ["ORTHOLOG_PATTERN", "ortholog_in_a_group_spec"]
