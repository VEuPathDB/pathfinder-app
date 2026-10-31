"""The toxodb strategy the spec-contradiction cases are measured on.

The tree and the ids are the ones a live turn wrote, so each case is a call
the execution agent really made.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue, to_wire
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.bound_values import bound

from ._strategy_edit_stubs import combine, leaf, seed

TM = "step_4f51bc4f"
SIGNAL = "step_044e4c5c"
PROFILE = "step_4951705a"
MIC2 = "step_780fd940"
RON2 = "step_fb1f017c"
TM_JOIN = "step_79b8b72b"
SIMILARITY_JOIN = "step_7eca55ff"
PROFILE_JOIN = "step_811d87da"
ROOT = "step_95c8dca2"

WDK_STEP_IDS = {
    TM: 101,
    SIGNAL: 102,
    PROFILE: 103,
    MIC2: 104,
    RON2: 105,
    TM_JOIN: 201,
    SIMILARITY_JOIN: 202,
    PROFILE_JOIN: 203,
    ROOT: 204,
}
_PATTERN = "%bbes:Y%btau:N%chom:Y%hsap:N%tgme:Y%"
PERCENTILE = "min_expression_percentile"
STATED_PERCENTILE: dict[str, ParamValue] = {PERCENTILE: NumberValue(value=90)}
DEPARTED_PERCENTILE: dict[str, ParamValue] = {PERCENTILE: NumberValue(value=80)}
SECOND_LOOK = "min_expression_percentile: the catalog turns this value down"


def records_the_call(
    seen: list[dict[str, ParamValue]],
) -> Callable[..., Awaitable[ValidatedParams]]:
    """A catalog that accepts every value and counts what it was asked."""

    async def _validate(*_args: Any, **kwargs: Any) -> ValidatedParams:
        params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
        seen.append(params)
        return ValidatedParams(params=params, record_class="transcript")

    return _validate


def refuses_a_second_look(
    seen: list[dict[str, ParamValue]],
) -> Callable[..., Awaitable[ValidatedParams]]:
    """A catalog that answers the write and turns down anything asked after it."""
    accept = records_the_call(seen)

    async def _validate(*args: Any, **kwargs: Any) -> ValidatedParams:
        if seen:
            raise ValidationError(title="Invalid value", detail=SECOND_LOOK)
        return await accept(*args, **kwargs)

    return _validate


def _decimal(value: ParamValue) -> StringValue:
    wire = to_wire(value)
    return StringValue(value=wire if "." in wire else f"{wire}.0")


async def writes_the_percentile_as_a_decimal(
    *_args: Any, **kwargs: Any
) -> ValidatedParams:
    """A catalog that rewrites the percentile, the way a number param is read."""
    params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
    held = params.get(PERCENTILE)
    if held is not None:
        params[PERCENTILE] = _decimal(held)
    return ValidatedParams(params=params, record_class="transcript")


async def cascades_from_the_size(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """A catalog whose percentile answers to the result size."""
    params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
    size = params.get("ProfileNumToReturn")
    if size is not None and to_wire(size) == "100":
        params[PERCENTILE] = NumberValue(value=80)
    return ValidatedParams(params=params, record_class="transcript")


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _joined(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _criteria() -> list[Criterion]:
    return [
        Criterion(id=TM, text="At least one predicted transmembrane domain"),
        Criterion(id=SIGNAL, text="Predicted signal peptide"),
        Criterion(
            id=PROFILE,
            text="Ortholog present in Apicomplexa and absent from Mammalia",
            resolved_params=bound({"profile_pattern": StringValue(value=_PATTERN)}),
        ),
        Criterion(
            id=MIC2,
            text="Cell-cycle expression profile similar to MIC2 (TGME49_201780)",
            resolved_params=bound(
                {"ProfileGeneId": StringValue(value="TGME49_201780")}
            ),
        ),
        Criterion(
            id=RON2,
            text="Cell-cycle expression profile similar to RON2 (TGME49_300100)",
            resolved_params=bound(
                {"ProfileGeneId": StringValue(value="TGME49_300100")}
            ),
        ),
    ]


def measured_deps(*, mic2_params: dict[str, ParamValue] | None = None) -> AgentDeps:
    """The strategy the spec built, and the spec that declares its shape."""
    deps = seed(
        combine(
            ROOT,
            combine(TM_JOIN, leaf(TM), leaf(SIGNAL), op=CombineOp.UNION),
            combine(
                PROFILE_JOIN,
                leaf(PROFILE),
                combine(
                    SIMILARITY_JOIN,
                    leaf(MIC2, mic2_params),
                    leaf(RON2),
                    CombineOp.UNION,
                ),
            ),
        ),
        wdk_step_ids=dict(WDK_STEP_IDS),
    )
    draft = deps.agent_state.operational_spec_draft
    draft.criteria = _criteria()
    draft.structure = SpecStructure(
        root=_joined(
            CombineOp.INTERSECT,
            _joined(CombineOp.UNION, _leaf(TM), _leaf(SIGNAL)),
            _joined(
                CombineOp.INTERSECT,
                _leaf(PROFILE),
                _joined(CombineOp.UNION, _leaf(MIC2), _leaf(RON2)),
            ),
        ),
    )
    return deps


def grounded_deps(mic2_params: dict[str, ParamValue]) -> AgentDeps:
    """The same strategy, with MIC2 holding a percentile a stated requirement
    grounds onto at 90, and the step holding ``mic2_params``."""
    deps = measured_deps(mic2_params=mic2_params)
    draft = deps.agent_state.operational_spec_draft
    draft.criteria = [
        c.model_copy(
            update={
                "search_name": "GenesByRNASeqEvidence",
                "resolved_params": bound(dict(STATED_PERCENTILE)),
            }
        )
        if c.id == MIC2
        else c
        for c in draft.criteria
    ]
    draft.constraints = [
        Constraint(
            kind=ConstraintKind.PERCENTILE,
            requested_value="top 10%",
            label="expression percentile",
            source=ConstraintSource.USER_EXPLICIT,
        )
    ]
    return deps


def union_of_the_same_three() -> StrategyStepNode:
    """The subtree the recovery pass wrote, keeping the step ids the spec names."""
    return combine(
        PROFILE_JOIN,
        leaf(PROFILE),
        combine(SIMILARITY_JOIN, leaf(MIC2), leaf(RON2), CombineOp.UNION),
        op=CombineOp.UNION,
    )
