from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict

from strategist.domain.eda_parts import EdaAnalysisState
from strategist.domain.private_inputs import inputs_for_viewer, is_account_dataset
from strategist.services.conversations.responses import ConversationResponse
from strategist.services.strategies.schemas import StepResponse

CONVERSATION_SHOWN: Final[frozenset[str]] = frozenset(
    {
        "name",
        "title",
        "description",
        "assistant_id",
        "site_id",
        "record_type",
        "steps",
        "root_step_id",
        "is_saved",
        "created_at",
        "updated_at",
        "step_count",
        "estimated_size",
        "strategy_revision",
        "mode",
    }
)
CONVERSATION_CLEARED: Final[Mapping[str, object]] = {
    "wdk_strategy_id": None,
    "wdk_strategy_created_here": False,
    "wdk_url": None,
    "gene_set_id": None,
    "dismissed_at": None,
    "total_tokens": 0,
    "total_cost_usd": Decimal(0),
    "parent_conversation_id": None,
    "parent_message_id": None,
}
STEP_SHOWN: Final[frozenset[str]] = frozenset(
    {
        "id",
        "kind",
        "display_name",
        "criterion_text",
        "search_name",
        "record_type",
        "operator",
        "colocation_params",
        "primary_input_step_id",
        "secondary_input_step_id",
        "estimated_size",
        "status",
        "is_filtered",
        "expanded_name",
    }
)
STEP_CLEARED: Final[Mapping[str, object]] = {
    "wdk_step_id": None,
    "expanded_strategy_id": None,
}
STEP_FILTERED: Final[frozenset[str]] = frozenset(
    {
        "parameters",
        "rationale",
        "filters",
        "analyses",
        "validation",
        "wdk_push_error",
    }
)
WITHHELD_PUSH_ERROR: Final = "This step failed on the site."
STUDY_SHOWN: Final[frozenset[str]] = frozenset(
    {
        "site_id",
        "dataset_id",
        "study_id",
        "analysis_id",
        "revision",
        "study_display_name",
        "display_name",
        "num_filters",
        "num_computations",
        "filters",
        "filter_summaries",
        "entity_counts",
        "compute",
        "modification_time",
    }
)
STUDY_CLEARED: Final[Mapping[str, object]] = {
    "analysis_url": None,
    "can_export_rows": False,
}

_ANALYSIS_STATE: Final = "data-eda.analysis-state"


class SharedContext(CamelModel):
    strategy: ConversationResponse
    study: EdaAnalysisState | None
    private_inputs: dict[str, list[str]]


class _Chunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = ""


class _StateChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["data-eda.analysis-state"]
    data: EdaAnalysisState


def _viewer_id(token: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"strategist:shared:{token}")


def _viewer_step(
    step: StepResponse, *, include_account_reads: bool
) -> tuple[StepResponse, list[str]]:
    inputs = inputs_for_viewer(
        step.parameters or {}, include_account_reads=include_account_reads
    )
    shown = step.model_copy(
        update={
            **STEP_CLEARED,
            "parameters": None if step.parameters is None else inputs.shown,
            "rationale": None
            if step.rationale is None
            else step.rationale.for_viewer(inputs),
            "filters": None
            if step.filters is None
            else [
                f.model_copy(update={"value": inputs.untyped(f.value, withheld=None)})
                for f in step.filters
            ],
            "analyses": None
            if step.analyses is None
            else [
                a.model_copy(
                    update={"parameters": inputs.untyped(a.parameters, withheld={})}
                )
                for a in step.analyses
            ],
            "validation": None
            if step.validation is None
            else step.validation.model_copy(update={"errors": None}),
            "wdk_push_error": None
            if step.wdk_push_error is None
            else WITHHELD_PUSH_ERROR,
        }
    )
    return shown, inputs.withheld


def viewer_strategy(
    detail: ConversationResponse, *, token: str, include_account_reads: bool
) -> tuple[ConversationResponse, dict[str, list[str]]]:
    read = [
        _viewer_step(step, include_account_reads=include_account_reads)
        for step in detail.steps
    ]
    shown = detail.model_copy(
        update={
            **CONVERSATION_CLEARED,
            "id": _viewer_id(token),
            "steps": [step for step, _ in read],
        }
    )
    return shown, {step.id: withheld for step, withheld in read if withheld}


def newest_study(
    chunks: Sequence[Mapping[str, Any]], analysis_id: str
) -> EdaAnalysisState | None:
    states = [
        _StateChunk.model_validate(raw).data
        for raw in chunks
        if _Chunk.model_validate(raw).type == _ANALYSIS_STATE
    ]
    return next(
        (state for state in reversed(states) if state.analysis_id == analysis_id),
        None,
    )


def viewer_study(
    state: EdaAnalysisState, *, include_account_reads: bool
) -> EdaAnalysisState | None:
    if is_account_dataset(state.dataset_id) and not include_account_reads:
        return None
    return state.model_copy(update=dict(STUDY_CLEARED))
