"""Service-layer strategy DTOs shared across services, AI, and transport."""

from collections.abc import Mapping

from veupathdb.domain.strategy import (
    StepAnalysis,
    StepSettings,
    StepValidation,
    StrategyStep,
    StrategyStepNode,
    settings_of,
)

from strategist.domain.strategy.build_outcome import citable_count
from strategist.domain.strategy.combine_naming import combine_name
from strategist.domain.strategy.record_class_check import step_class_of
from strategist.domain.strategy.step_rationale import AnalysisRationale, StepRationale
from strategist.domain.strategy.step_status import StepStatus, step_status
from strategist.domain.strategy.step_words import StepWords
from strategist.domain.strategy.types import SyncStateProtocol
from strategist.services.eda.export import exported_analysis


class StepFields(StepSettings):
    """Strategy step - its settings and the view fields beside them."""

    id: str
    kind: str | None = None
    display_name: str | None = None
    # The researcher's words the step stands for; the title names the search.
    criterion_text: str | None = None
    # Why the step runs what it runs: its analysis's compute, else the search choice.
    rationale: StepRationale | None = None
    record_type: str | None = None
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
    analyses: list[StepAnalysis] | None = None


class StepResponse(StepFields):
    """Strategy step - WDK-aligned fields."""


def step_rationale_of(
    words: StepWords, step: StrategyStep | StrategyStepNode
) -> StepRationale | None:
    """Why the step runs what it runs: its analysis document, else the stored choice."""
    kind = words.kind_of(step.id, step.search_name)
    binding = exported_analysis(kind, step.parameters)
    if binding is not None:
        return AnalysisRationale.of(binding)
    return words.rationale_of(step.id, step.search_name)


def step_response(
    step: StrategyStep,
    *,
    steps: Mapping[str, StrategyStep],
    record_type: str | None,
    words: StepWords,
    sync: SyncStateProtocol | None,
) -> StepResponse:
    wdk_step_id = sync.wdk_step_ids.get(step.id) if sync else None
    validation = sync.step_validations.get(step.id) if sync else None
    return StepResponse.model_validate(
        {
            **settings_of(step).model_dump(),
            "id": step.id,
            "kind": step.kind.value,
            "display_name": (
                combine_name(step.display_name, step.search_name, step.operator)
                or step.display_label
            ),
            "criterion_text": words.criterion_texts.get(step.id),
            "rationale": step_rationale_of(words, step),
            "record_type": step_class_of(steps, step.id) or record_type,
            "primary_input_step_id": step.primary_input_id,
            "secondary_input_step_id": step.secondary_input_id,
            "estimated_size": (
                citable_count(
                    step.id, counts=sync.step_counts, refused=sync.wdk_push_errors
                )
                if sync
                else None
            ),
            "wdk_step_id": wdk_step_id,
            "status": step_status(
                step,
                wdk_step_id=wdk_step_id,
                validation=validation,
                has_open_params=False,
            ),
            "is_filtered": bool(step.filters),
            "wdk_push_error": sync.wdk_push_errors.get(step.id) if sync else None,
            "validation": validation,
            "analyses": step.analyses or None,
        }
    )
