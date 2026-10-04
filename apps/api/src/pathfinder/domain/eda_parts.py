"""Typed payloads for the data-eda parts the chat and the tab both render."""

from __future__ import annotations

import re
from typing import Literal

from assistant_core.platform.pydantic_base import computed
from pydantic import Field, JsonValue, model_serializer, model_validator
from pydantic_core.core_schema import SerializerFunctionWrapHandler
from veupathdb.model import CamelModel

EdaFilterType = Literal[
    "stringSet",
    "numberSet",
    "dateSet",
    "numberRange",
    "dateRange",
    "longitudeRange",
    "multiFilter",
]


class EdaFilterSheetEntry(CamelModel):
    """One variable, with everything needed to write a filter for it.

    The sheet is read by a model, so a field a variable does not declare is
    not sent: the entity tree and the variable type it was derived from are
    read from ``describe_eda_study``.
    """

    entity_id: str
    entity_display_name: str = ""
    variable_id: str
    display_name: str
    filter_type: EdaFilterType
    is_multi_valued: bool = False
    vocabulary: list[str] = Field(default_factory=list)
    vocabulary_total: int = 0
    vocabulary_note: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    date_min: str | None = None
    date_max: str | None = None
    sub_filter_variable_ids: list[str] = Field(default_factory=list)
    example: dict[str, JsonValue] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _what_the_variable_declares(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, JsonValue]:
        """A field with no value says nothing, so it is not serialized."""
        dumped: dict[str, JsonValue] = handler(self)
        return {
            name: value
            for name, value in dumped.items()
            if value is not None and value not in ([], "", {})
        }


class OpenEdaSheet(CamelModel):
    """The filter sheet a thread holds open, and the study it describes."""

    dataset_id: str
    entries: list[EdaFilterSheetEntry] = Field(default_factory=list)


class EdaEntityCount(CamelModel):
    """One entity's subset size against its unfiltered size."""

    entity_id: str
    entity_display_name: str
    count: int = Field(ge=0)
    unfiltered_count: int = Field(ge=0)


class EdaComputeSummary(CamelModel):
    """The analysis's comparison, each variable by the name the study gives it."""

    method: str
    identifier_variable: str
    value_variable: str
    comparator_variable: str
    group_a: list[str]
    group_b: list[str]


class EdaAnalysisState(CamelModel):
    """The open analysis, as both surfaces re-render it after every mutation.

    ``revision`` is the mutation counter of the binding; ``None`` means
    unknown and the store's reconcile rule then takes the last write.
    ``filters`` entries are the wire filter objects, kept as JSON because
    this package cannot import the integrations union. ``analysis_url`` opens
    the analysis in the site's own explorer; the thread log holds parts that
    carry none, so it is optional. ``compute`` is the comparison the analysis
    holds, or None when it holds none. ``modification_time`` is the time the
    service stamped on the document this state was read from; a part logged
    before it was recorded carries None.
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
    analysis_url: str | None = None
    compute: EdaComputeSummary | None = None
    modification_time: str | None = None


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


class EdaComparison(CamelModel):
    """The labels of the two sample groups one compute compares.

    ``group_a`` is the reference, so a positive effect size is higher in
    ``group_b``.
    """

    group_a: list[str]
    group_b: list[str]


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
    retained_point_ids: list[str] = Field(
        description=(
            "Every point id the cut retains, in the service's order. The "
            "points are capped for the plot; this list is not."
        ),
    )
    caption: str = Field(
        default="",
        description=(
            "One sentence the model wrote about the plot. Empty when it "
            "wrote none, and the figure is then captioned from the numbers "
            "alone."
        ),
    )
    comparison: EdaComparison | None = Field(
        default=None,
        description=(
            "The two groups the plot compares. The thread log holds plots "
            "that carry none."
        ),
    )


EdaStatisticKind = Literal["two_by_two", "contingency", "boxplot", "trend"]


# The share a component's label states, as in "PC 1 (54.35% variance)".
_STATED_SHARE = re.compile(r"\((\d+(?:\.\d+)?%)(?: variance)?\)\s*$")


class EdaPcaAxis(CamelModel):
    """One principal component, by the name the compute gives it."""

    variable_id: str
    display_name: str

    @property
    def stated_share(self) -> str:
        """The share of variance the label states, or the label when it states none."""
        found = _STATED_SHARE.search(self.display_name)
        return self.display_name if found is None else found.group(1)


class EdaPcaSeries(CamelModel):
    """The samples of one overlay value, each at its place on the two axes.

    The service sends each coordinate as text, and the fields read it as a number.
    """

    label: str
    x: list[float]
    y: list[float]
    sample_ids: list[str]

    @model_validator(mode="after")
    def _one_place_per_sample(self) -> EdaPcaSeries:
        if not len(self.x) == len(self.y) == len(self.sample_ids):
            msg = "x, y and sample_ids must be the same length"
            raise ValueError(msg)
        return self


class EdaPcaPart(CamelModel):
    """The samples on the first two components of a dimensionality reduction."""

    statistic_id: str
    dataset_id: str
    analysis_id: str
    axes: list[EdaPcaAxis] = Field(min_length=2, max_length=2)
    series: list[EdaPcaSeries]
    caption: str = ""

    @computed
    def sample_count(self) -> int:
        return sum(len(series.sample_ids) for series in self.series)

    @computed
    def group_count(self) -> int:
        return len(self.series)


class EdaStatisticRow(CamelModel):
    """One statistic the service returned, in the text the service gave it. A
    test the service reports only a p-value for has no value."""

    name: str
    value: str | None
    p_value: str | None
    confidence_interval: str | None


class EdaCountTable(CamelModel):
    """The records of each pair of values: ``matrix[i][j]`` counts x label ``i``
    with y label ``j``."""

    x_labels: list[str]
    y_labels: list[str]
    matrix: list[list[int]]

    @model_validator(mode="after")
    def _one_cell_per_pair(self) -> EdaCountTable:
        widths = {len(row) for row in self.matrix}
        if len(self.matrix) != len(self.x_labels) or widths - {len(self.y_labels)}:
            msg = "matrix must hold one row per x label and one cell per y label"
            raise ValueError(msg)
        return self


class EdaBoxplotBox(CamelModel):
    """The five numbers of one group, its mean when asked, and its outliers."""

    label: str
    lower_fence: float
    q1: float
    median: float
    q3: float
    upper_fence: float
    mean: float | None
    outlier_count: int = Field(ge=0)


class EdaTrend(CamelModel):
    """The points of two continuous variables and the line fit through them,
    with each axis named as the study names its variable.

    The service sends the coordinates as text, and the fields read them as numbers.
    """

    x_label: str
    y_label: str
    x: list[float]
    y: list[float]
    line_x: list[float]
    line_y: list[float]


class EdaStatisticsReading(CamelModel):
    """What one statistics read of the service returned."""

    rows: list[EdaStatisticRow]
    table: EdaCountTable | None
    boxes: list[EdaBoxplotBox]
    trend: EdaTrend | None


class EdaStatisticsPart(EdaStatisticsReading):
    """A statistic the service computed on the open analysis, with its title."""

    statistic_id: str
    dataset_id: str
    analysis_id: str
    kind: EdaStatisticKind
    title: str
    caption: str = ""
