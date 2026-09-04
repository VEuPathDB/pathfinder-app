"""Request and response shapes of the EDA routes."""

from __future__ import annotations

from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import ConfigDict, Discriminator, Field

from pathfinder.domain.eda_parts import EdaAnalysisState, EdaEffectDirection
from pathfinder.services.eda import EdaComputationDescriptor, EdaFilter
from pathfinder.services.eda.compute import VolcanoThresholds


class EdaStudySummaryResponse(CamelModel):
    """One study as the tab's picker lists it."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: str
    study_id: str
    display_name: str
    short_display_name: str
    description: str
    source_type: str
    relevance: float
    can_subset: bool
    can_export_rows: bool


class EdaStudyListResponse(CamelModel):
    studies: list[EdaStudySummaryResponse]


class EdaVariableResponse(CamelModel):
    """One filterable variable, with the exact filter type it takes."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    variable_id: str
    display_name: str
    variable_type: str
    filter_type: str | None
    data_shape: str | None
    is_multi_valued: bool
    vocabulary: list[str]
    vocabulary_total: int
    vocabulary_note: str | None
    range_min: float | None
    range_max: float | None
    date_min: str | None
    date_max: str | None
    sub_filter_variable_ids: list[str]
    hide_from: list[str]


class EdaEntityResponse(CamelModel):
    """One table of records in the study's tree."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    display_name: str
    display_name_plural: str
    parent_entity_id: str | None
    variable_count: int
    has_gene_id: bool


class EdaStudyDetailResponse(CamelModel):
    """A study's entity tree and its filterable variables."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: str
    study_id: str
    display_name: str
    entities: list[EdaEntityResponse]
    variables: list[EdaVariableResponse]
    gene_entity_id: str | None
    gene_entity_problem: str | None
    can_subset: bool
    can_export_rows: bool


class EdaCountRequest(CamelModel):
    """Count one entity's records under a filter array."""

    dataset_id: str
    entity_id: str
    filters: list[EdaFilter] = Field(default_factory=list)


class EdaCountResponse(CamelModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    count: int
    unfiltered_count: int


class EdaDistributionRequest(CamelModel):
    """One variable's histogram under a filter array."""

    dataset_id: str
    entity_id: str
    variable_id: str
    filters: list[EdaFilter] = Field(default_factory=list)


class EdaVizRequest(CamelModel):
    """The volcano the bound analysis's compute already produced."""

    dataset_id: str
    chart: Literal["volcano"]
    effect_size_threshold: float = 1.0
    significance_threshold: float = 0.05
    effect_direction: EdaEffectDirection = "upAndDown"


class EdaVizPointResponse(CamelModel):
    """One gene on the volcano. A point may carry no adjusted p-value."""

    model_config = ConfigDict(from_attributes=True)

    point_id: str
    effect_size: float
    p_value: float | None
    adjusted_p_value: float | None
    retained: bool


class EdaVizResponse(CamelModel):
    chart: Literal["volcano"]
    effect_size_label: str
    effect_size_threshold: float
    significance_threshold: float
    effect_direction: EdaEffectDirection
    total_points: int
    retained_points: int
    points: list[EdaVizPointResponse]


class ConversationEdaResponse(CamelModel):
    """The thread's bound analysis, as the tab hydrates from it.

    ``analysis`` is the same state the PATCH answers and the
    ``data-eda.analysis-state`` part carry, so one reducer serves all three.
    Both keys are always present and nullable; both are null on a thread with
    no analysis open.
    """

    analysis: EdaAnalysisState | None
    descriptor: JSONObject | None


class EdaBindAction(CamelModel):
    """Open an analysis on a study and bind it to this thread."""

    action: Literal["bind"]
    site_id: str
    dataset_id: str
    purpose: str = "EDA analysis"


class EdaSetFiltersAction(CamelModel):
    """Replace the bound analysis's subset."""

    action: Literal["set-filters"]
    filters: list[EdaFilter] = Field(default_factory=list)


class EdaRunComputeAction(CamelModel):
    """Submit or poll the analysis's compute. Idempotent per input hash."""

    action: Literal["run-compute"]
    computation: EdaComputationDescriptor


class EdaExportStepAction(CamelModel):
    """Export the analysis's genes as a step in the thread's strategy."""

    action: Literal["export-step"]
    thresholds: VolcanoThresholds | None = None


class EdaUnbindAction(CamelModel):
    """Clear the thread's binding. The upstream analysis is kept.

    Unbinding an unbound thread answers 200 with a null analysis; the only
    404 in the handler is the ownership check.
    """

    action: Literal["unbind"]


ConversationEdaPatchRequest = Annotated[
    EdaBindAction
    | EdaSetFiltersAction
    | EdaRunComputeAction
    | EdaExportStepAction
    | EdaUnbindAction,
    Discriminator("action"),
]


class EdaJobRefResponse(CamelModel):
    """The compute job a run-compute action addressed."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str
    task_id: str | None
    app_name: str
    status: str


class EdaAnalysisPatchResponse(CamelModel):
    """Every PATCH answers with the analysis state the surfaces re-render from.

    ``analysis`` is always present and nullable, never omitted.
    """

    analysis: EdaAnalysisState | None
    job: EdaJobRefResponse | None
    step: JSONObject | None
