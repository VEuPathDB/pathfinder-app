from __future__ import annotations

from veupathdb.domain.parameters import (
    ParamValue,
    StringValue,
    param_value_from_raw,
)

from strategist.ai.lead.parameter_facts import step_parameters
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    CountOp,
    CountValue,
    PercentileEnd,
    PercentileValue,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    RequirementLink,
    ValueSource,
)
from strategist.domain.turn_facts import StepFact


def bound_value(
    value: ParamValue,
    source: ValueSource,
    shown: str,
    *,
    number: bool = True,
    visible: bool = True,
    published: tuple[float | None, float | None] = (None, None),
) -> BoundValue:
    return BoundValue(
        value=value,
        source=source,
        display_name=shown,
        number=number,
        visible=visible,
        published_min=published[0],
        published_max=published[1],
    )


def range_of(low: float, high: float) -> ParamValue:
    return param_value_from_raw({"min": low, "max": high}, "number-range")


def text_value(wire: str) -> StringValue:
    return StringValue(value=wire)


def count_of(feature: str, op: CountOp, number: float, said: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COUNT,
        requested_value=said,
        label=feature,
        value=CountValue(feature=feature, op=op, value=number),
    )


def percentile_of(end: PercentileEnd, share: float, said: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.PERCENTILE,
        requested_value=said,
        label="percentile",
        value=PercentileValue(end=end, share=share),
    )


def step_lines(
    values: dict[str, BoundValue],
    links: dict[str, Constraint],
    held: list[Constraint] | None = None,
) -> list[str]:
    criterion = Criterion(
        id="c1",
        text="the criterion",
        search_name="ASearch",
        answers=[
            RequirementLink(requirement=c.id, param=param) for param, c in links.items()
        ],
        resolved_params=values,
    )
    rows = step_parameters(
        criterion,
        "gene",
        [],
        list(links.values()) if held is None else held,
    )
    return StepFact(step_id="c1", display_name="A", parameters=rows).lines()[1:]
