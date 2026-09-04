"""Typed payloads for the data-eda parts the chat and the tab both render."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, JsonValue, model_validator


class EdaEntityCount(CamelModel):
    """One entity's subset size against its unfiltered size."""

    entity_id: str
    entity_display_name: str
    count: int = Field(ge=0)
    unfiltered_count: int = Field(ge=0)


class EdaAnalysisState(CamelModel):
    """The open analysis, as both surfaces re-render it after every mutation.

    ``revision`` is the mutation counter of the binding; ``None`` means
    unknown and the store's reconcile rule then takes the last write.
    ``filters`` entries are the wire filter objects, kept as JSON because
    this package cannot import the integrations union.
    """

    site_id: str
    dataset_id: str
    study_id: str
    analysis_id: str
    revision: int | None
    study_display_name: str
    display_name: str
    num_filters: int = Field(ge=0)
    num_computations: int = Field(ge=0)
    filters: list[dict[str, JsonValue]]
    filter_summaries: list[str]
    entity_counts: list[EdaEntityCount]
    can_export_rows: bool


class EdaDistributionSeries(CamelModel):
    """One variable's histogram under the current subset.

    ``num_var_values`` can exceed ``subset_size`` on a multi-valued variable,
    so a percentage needs its denominator named.
    """

    variable_id: str
    variable_display_name: str
    labels: list[str]
    values: list[float]
    subset_size: int = Field(ge=0)
    num_var_values: int = Field(ge=0)
    num_missing_cases: int = Field(ge=0)
    is_multi_valued: bool

    @model_validator(mode="after")
    def _one_value_per_label(self) -> EdaDistributionSeries:
        if len(self.labels) != len(self.values):
            msg = "labels and values must be the same length"
            raise ValueError(msg)
        return self


class EdaSubsetPreviewPart(CamelModel):
    """What the current filters select, with one variable's shape."""

    dataset_id: str
    analysis_id: str
    entity_counts: list[EdaEntityCount]
    distribution: EdaDistributionSeries | None
    distribution_note: str | None
    caption: str = Field(
        default="",
        description=(
            "One sentence the model wrote about the plot. Empty when it "
            "wrote none, and the figure is then captioned from the numbers "
            "alone."
        ),
    )


EdaEffectDirection = Literal["upOnly", "downOnly", "upAndDown"]


class EdaVolcanoPoint(CamelModel):
    """One gene on the volcano. A point may carry no p-value."""

    point_id: str
    effect_size: float
    p_value: float | None
    adjusted_p_value: float | None
    retained: bool


class EdaVizPart(CamelModel):
    """Server-computed plot data, sized for one chart."""

    dataset_id: str
    analysis_id: str
    chart: Literal["volcano", "histogram", "boxplot", "bar", "scatter"]
    effect_size_label: str
    effect_size_threshold: float | None
    significance_threshold: float | None
    effect_direction: EdaEffectDirection | None
    total_points: int = Field(ge=0)
    retained_points: int = Field(ge=0)
    points: list[EdaVolcanoPoint]
    caption: str = Field(
        default="",
        description=(
            "One sentence the model wrote about the plot. Empty when it "
            "wrote none, and the figure is then captioned from the numbers "
            "alone."
        ),
    )
