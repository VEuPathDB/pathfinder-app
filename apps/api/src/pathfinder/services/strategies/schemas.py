"""Service-layer strategy DTOs shared across services, AI, and transport."""

from assistant_core.platform.pydantic_base import CamelModel

from pathfinder.domain.parameters.values import ParamValue
from pathfinder.domain.strategy.ast import (
    StepAnalysis,
    StepFilter,
    StepReport,
    StrategyStepNode,
)
from pathfinder.domain.strategy.graph_model import (
    StepStatus,
    flatten_tree,
    step_status,
)
from pathfinder.domain.strategy.ops import ColocationParams
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.domain.strategy.validation import StepValidation


class StepResponse(CamelModel):
    """Strategy step — WDK-aligned fields."""

    id: str
    kind: str | None = None
    display_name: str | None = None
    search_name: str | None = None
    record_type: str | None = None
    parameters: dict[str, ParamValue] | None = None
    operator: str | None = None
    colocation_params: ColocationParams | None = None
    primary_input_step_id: str | None = None
    secondary_input_step_id: str | None = None
    estimated_size: int | None = None
    wdk_step_id: int | None = None
    status: StepStatus = StepStatus.DRAFT
    """Draft / ready / built / invalid, derived in one place.

    Replaces ``is_built``, which only answered "does WDK have a row for this".
    It could not say a step is deliberately unfinished, so the canvas kept its
    own notion and the push planner inferred a third.
    """
    is_filtered: bool = False
    wdk_push_error: str | None = None
    validation: StepValidation | None = None
    filters: list[StepFilter] | None = None
    analyses: list[StepAnalysis] | None = None
    reports: list[StepReport] | None = None
    expanded_strategy_id: int | None = None
    expanded_name: str | None = None


def step_response_from_strategy_ast(
    payload: StrategyAst, step: StrategyStepNode
) -> StepResponse:
    counts = payload.step_counts or {}
    ids = payload.wdk_step_ids or {}
    validations = payload.step_validations or {}

    wdk_step_id = ids.get(step.id)
    if wdk_step_id is None and step.id.isdigit():
        wdk_step_id = int(step.id)

    return StepResponse(
        id=step.id,
        kind=step.infer_kind(),
        display_name=step.display_label,
        search_name=step.search_name,
        record_type=payload.record_type,
        parameters=step.parameters,
        operator=step.operator.value if step.operator else None,
        colocation_params=step.colocation_params,
        primary_input_step_id=step.primary_input_id,
        secondary_input_step_id=step.secondary_input_id,
        estimated_size=counts.get(step.id),
        wdk_step_id=wdk_step_id,
        status=step_status(
            flatten_tree(step)[step.id],
            wdk_step_id=wdk_step_id,
            validation=validations.get(step.id),
            has_open_params=False,
        ),
        wdk_push_error=(payload.wdk_push_errors or {}).get(step.id),
        is_filtered=bool(step.filters),
        validation=validations.get(step.id),
        filters=step.filters or None,
        analyses=step.analyses or None,
        reports=step.reports or None,
        expanded_strategy_id=step.expanded_strategy_id,
        expanded_name=step.expanded_name,
    )
