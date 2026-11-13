from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.parameters import StringValue

from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    RequirementValue,
)
from strategist.domain.strategy.operational_spec import Criterion, RequirementLink
from strategist.tests._support.bound_values import bound

PERCENTILE_SEARCH = "GenesByRNASeqPfal3D7_Stunnenberg_RSRCPercentile"


def requirement(
    kind: ConstraintKind, value: RequirementValue | None, words: str = "asked"
) -> Constraint:
    return Constraint(
        id=f"r_{kind.value}",
        kind=kind,
        requested_value=words,
        label=words,
        source=ConstraintSource.USER_EXPLICIT,
        value=value,
    )


def linked(
    held: Constraint,
    values: Mapping[str, str],
    *params: str | None,
    search: str = PERCENTILE_SEARCH,
    shown: Mapping[str, str] | None = None,
) -> Criterion:
    return Criterion(
        id="c_linked",
        text="the linked criterion",
        search_name=search,
        resolved_params=bound(
            {name: StringValue(value=raw) for name, raw in values.items()}
        ),
        param_display_names=dict(shown or {}),
        answers=[RequirementLink(requirement=held.id, param=p) for p in params],
    )
