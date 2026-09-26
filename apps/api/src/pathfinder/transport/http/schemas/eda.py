"""Request and response shapes of the EDA routes."""

from __future__ import annotations

from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import ConfigDict, Discriminator

from pathfinder.domain.eda_parts import (
    EdaAnalysisState,
    EdaComparison,
    EdaEffectDirection,
)


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
    # The genomics sites that publish the study, ["portal"] when none does, and
    # empty when the index that knows them does not answer.
    sites: list[str]
    # Why the study does not open on this site, or None when it does.
    not_here: str | None


class EdaStudyListResponse(CamelModel):
    studies: list[EdaStudySummaryResponse]


class EdaVizRequest(CamelModel):
    """The volcano the bound analysis's compute already produced."""

    chart: Literal["volcano"]


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
    retained_point_ids: list[str]
    points: list[EdaVizPointResponse]
    comparison: EdaComparison


class ConversationEdaResponse(CamelModel):
    """The conversation's bound analysis, as the tab hydrates from it.

    ``analysis`` is the same state the PATCH answers and the
    ``data-eda.analysis-state`` part carry, so one reducer serves all three.
    The key is always present, and null when no analysis is open.
    """

    analysis: EdaAnalysisState | None


class EdaBindAction(CamelModel):
    """Open an analysis on a study and bind it to this thread."""

    action: Literal["bind"]
    site_id: str
    dataset_id: str
    purpose: str = "EDA analysis"


class EdaExportStepAction(CamelModel):
    """Export the analysis's genes as a step in the thread's strategy.

    ``volcano`` exports the genes of the cut the analysis stores; ``subset``
    exports the genes its filters keep.
    """

    action: Literal["export-step"]
    source: Literal["volcano", "subset"]


class EdaUnbindAction(CamelModel):
    """Clear the thread's binding. The upstream analysis is kept.

    Unbinding an unbound thread answers 200 with a null analysis; the only
    404 in the handler is the ownership check.
    """

    action: Literal["unbind"]


ConversationEdaPatchRequest = Annotated[
    EdaBindAction | EdaExportStepAction | EdaUnbindAction,
    Discriminator("action"),
]


class EdaAnalysisPatchResponse(CamelModel):
    """Every PATCH answers with the analysis state the surfaces re-render from.

    ``analysis`` is always present and nullable, never omitted.
    """

    analysis: EdaAnalysisState | None
    step: JSONObject | None
