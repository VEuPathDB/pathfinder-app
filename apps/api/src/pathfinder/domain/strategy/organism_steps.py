from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from pathfinder.domain.strategy.constraints import (
    GENE_ANSWERING_CLASSES,
    Constraint,
    ConstraintKind,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.organism_scope import selected_organisms
from pathfinder.domain.strategy.requirement_reports import (
    RequirementReport,
    numbered_requirements,
)

UNMARKED_ORGANISM_PARAMS: Mapping[str, str] = MappingProxyType(
    {"ByTaxonomy": "taxon_type_ahead"}
)


def limits_to_an_organism(criterion: Criterion) -> bool:
    if selected_organisms(criterion) or criterion.dataset_organisms:
        return True
    if any(b.value.type == "input-dataset" for b in criterion.resolved_params.values()):
        return True
    param = UNMARKED_ORGANISM_PARAMS.get(criterion.search_name)
    held = None if param is None else criterion.resolved_params.get(param)
    return held is not None and not held.unset


def organisms_no_step_limits(
    requirements: Sequence[Constraint],
    reports: Sequence[RequirementReport],
    spec: OperationalSpec,
) -> list[str]:
    if spec.record_type not in GENE_ANSWERING_CLASSES:
        return []
    if any(limits_to_an_organism(c) for c in spec.criteria):
        return []
    reported = {report.requirement for report in reports}
    return [
        number
        for number, requirement in numbered_requirements(requirements).items()
        if requirement.kind is ConstraintKind.ORGANISM and number not in reported
    ]


__all__ = [
    "UNMARKED_ORGANISM_PARAMS",
    "limits_to_an_organism",
    "organisms_no_step_limits",
]
