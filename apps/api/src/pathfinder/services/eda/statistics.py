"""The statistics the EDA service computes on an analysis's subset, read back
typed, one read per kind."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from assistant_core.graph.tool_summary import count_noun
from veupathdb.domain import EntityFacts, entity_by_id, variable_by_id
from veupathdb.eda import (
    EdaBadRequestError,
    EdaBoxplotConfig,
    EdaContTableResponse,
    EdaFilter,
    EdaMosaicConfig,
    EdaScatterplotConfig,
    EdaScatterplotSeries,
    EdaStudyDetail,
    EdaTwoByTwoConfig,
    EdaTwoByTwoResponse,
    EdaTwoByTwoStatistic,
    EdaVariableSpec,
    get_eda_client,
)

from pathfinder.domain.eda_parts import (
    EdaBoxplotBox,
    EdaCountTable,
    EdaStatisticKind,
    EdaStatisticRow,
    EdaStatisticsPart,
    EdaStatisticsReading,
    EdaTrend,
)
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.statistic_facts import statistic_id
from pathfinder.services.eda.description import display_names

_TESTS: dict[EdaStatisticKind, str] = {
    "two_by_two": "Two-by-two table",
    "contingency": "Contingency table",
    "boxplot": "Box plot",
    "trend": "Best-fit line",
}


class StatisticsRefusedError(ValueError):
    """The request names something the study or the statistic cannot read."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__(" ".join(messages))
        self.messages = messages


@dataclass(frozen=True, slots=True)
class StatisticsRequest:
    """One statistic of two variables, on the records of one entity."""

    kind: EdaStatisticKind
    x: EdaVariableSpec
    y: EdaVariableSpec
    output_entity_id: str
    x_reference_value: str | None = None
    y_reference_value: str | None = None
    color_by: EdaVariableSpec | None = None

    def variables(self) -> list[EdaVariableSpec]:
        return [self.x, self.y, *([] if self.color_by is None else [self.color_by])]

    def statistic_id(self) -> str:
        named = [f"{v.entity_id}.{v.variable_id}" for v in self.variables()]
        held = [r for r in (self.x_reference_value, self.y_reference_value) if r]
        return statistic_id(self.kind, [self.output_entity_id, *named, *held])


def lineage(study: EdaStudyDetail, entity_id: str) -> list[str]:
    """The entity ids from the root down to ``entity_id``, or none when the
    study declares no such entity."""

    def down(entity: EntityFacts) -> list[str]:
        if entity.id == entity_id:
            return [entity.id]
        for child in entity.children:
            below = down(child)
            if below:
                return [entity.id, *below]
        return []

    return down(study.root_entity)


def request_errors(study: EdaStudyDetail, request: StatisticsRequest) -> list[str]:
    """Every variable the study does not declare or the entity cannot read.

    A plot reads a variable of its own entity or of an ancestor of it.
    """
    readable = lineage(study, request.output_entity_id)
    if not readable:
        return [f"Study {study.id} declares no entity {request.output_entity_id}."]
    errors = [
        f"{v.entity_id} is not {request.output_entity_id} or an ancestor of it, so "
        f"a {request.kind} of {request.output_entity_id} cannot read {v.variable_id}. "
        f"The readable entities are {', '.join(readable)}."
        for v in request.variables()
        if v.entity_id not in readable
    ]
    errors.extend(
        f"Entity {v.entity_id} declares no variable {v.variable_id}."
        for v in request.variables()
        if v.entity_id in readable and not declared(study, v)
    )
    if request.color_by is not None and request.kind != "boxplot":
        errors.append(f"color_by_variable groups a boxplot; a {request.kind} has none.")
    return errors


def declared(study: EdaStudyDetail, spec: EdaVariableSpec) -> bool:
    """Whether the study declares the variable on the entity the spec names."""
    entity = entity_by_id(study.root_entity, spec.entity_id)
    return entity is not None and variable_by_id(entity, spec.variable_id) is not None


def _shown(number: float | str | None) -> str | None:
    """A number in the text the service gave it, a whole number without a point."""
    match number:
        case float() if number.is_integer():
            return str(int(number))
        case None:
            return None
        case _:
            return str(number)


def _row(name: str, statistic: EdaTwoByTwoStatistic | None) -> list[EdaStatisticRow]:
    if statistic is None:
        return []
    return [
        EdaStatisticRow(
            name=name,
            value=_shown(statistic.value),
            p_value=statistic.pvalue,
            confidence_interval=statistic.confidence_interval,
        )
    ]


def _plain_row(
    name: str, value: float | str | None, *, p_value: str | None = None
) -> EdaStatisticRow:
    return EdaStatisticRow(
        name=name, value=_shown(value), p_value=p_value, confidence_interval=None
    )


def _count_table(response: EdaContTableResponse | EdaTwoByTwoResponse) -> EdaCountTable:
    counts = response.counts
    columns = {tuple(labels) for labels in counts.y_label}
    if len(columns) > 1:
        msg = "The service gave each x label different y labels."
        raise RuntimeError(msg)
    return EdaCountTable(
        x_labels=counts.x_label,
        y_labels=[*next(iter(columns), ())],
        matrix=counts.value,
    )


async def two_by_two(
    site_id: str,
    *,
    study_id: str,
    filters: Sequence[EdaFilter],
    config: EdaTwoByTwoConfig,
) -> EdaStatisticsReading:
    """The 2x2 table and every statistic the service returned for it.

    A table the service cannot evaluate is refused; the contingency table of
    the same two variables still answers.
    """
    try:
        response = await get_eda_client(site_id).two_by_two(
            study_id=study_id, filters=filters, config=config
        )
    except EdaBadRequestError as exc:
        msg = (
            "The site cannot compute a two-by-two table on this study. The "
            "contingency table of the same two variables answers chi-squared, "
            "degrees of freedom and p."
        )
        raise StatisticsRefusedError([msg]) from exc
    named = (
        ("chi-squared", response.chi_sq),
        ("Fisher's exact", response.fisher),
        ("odds ratio", response.odds_ratio),
        ("relative risk", response.relative_risk),
        ("prevalence", response.prevalence),
        ("sensitivity", response.sensitivity),
        ("specificity", response.specificity),
        ("positive predictive value", response.pos_predictive_value),
        ("negative predictive value", response.neg_predictive_value),
    )
    return EdaStatisticsReading(
        rows=[row for name, statistic in named for row in _row(name, statistic)],
        table=_count_table(response),
        boxes=[],
        trend=None,
    )


async def contingency(
    site_id: str,
    *,
    study_id: str,
    filters: Sequence[EdaFilter],
    config: EdaMosaicConfig,
) -> EdaStatisticsReading:
    """The table and the chi-squared test of independence on it."""
    response = await get_eda_client(site_id).contingency_table(
        study_id=study_id, filters=filters, config=config
    )
    rows = [
        _plain_row("chi-squared", response.chisq, p_value=_shown(response.pvalue)),
        _plain_row("degrees of freedom", response.degrees_freedom),
    ]
    return EdaStatisticsReading(
        rows=rows, table=_count_table(response), boxes=[], trend=None
    )


async def boxplot(
    site_id: str,
    *,
    study_id: str,
    filters: Sequence[EdaFilter],
    config: EdaBoxplotConfig,
) -> EdaStatisticsReading:
    """The five numbers, the mean and the outliers of each group."""
    response = await get_eda_client(site_id).boxplot(
        study_id=study_id, filters=filters, config=config
    )
    return EdaStatisticsReading(
        rows=[],
        table=None,
        boxes=[
            EdaBoxplotBox(
                label=group.label
                if series.overlay_variable_details is None
                else f"{group.label}, {series.overlay_variable_details.value}",
                lower_fence=group.lowerfence,
                q1=group.q1,
                median=group.median,
                q3=group.q3,
                upper_fence=group.upperfence,
                mean=group.mean,
                outlier_count=len(group.outliers),
            )
            for series in response.data
            for group in series.groups
        ],
        trend=None,
    )


async def trend(
    site_id: str,
    *,
    study_id: str,
    filters: Sequence[EdaFilter],
    config: EdaScatterplotConfig,
    axis_names: tuple[str, str],
) -> EdaStatisticsReading:
    """The points, the line the service fit through them, and its r-squared."""
    response = await get_eda_client(site_id).scatterplot(
        app="pass", study_id=study_id, filters=filters, config=config
    )
    series = next(iter(response.data), EdaScatterplotSeries())
    return EdaStatisticsReading(
        rows=[
            _plain_row("r-squared", series.r2),
            _plain_row("points", count_noun(len(series.series_x), "point")),
        ],
        table=None,
        boxes=[],
        trend=EdaTrend.model_validate(
            {
                "x_label": axis_names[0],
                "y_label": axis_names[1],
                "x": series.series_x,
                "y": series.series_y,
                "line_x": series.best_fit_line_x,
                "line_y": series.best_fit_line_y,
            }
        ),
    )


async def _reading(
    site_id: str,
    *,
    study: EdaStudyDetail,
    filters: Sequence[EdaFilter],
    request: StatisticsRequest,
) -> EdaStatisticsReading:
    study_id = study.id
    axes = {
        "output_entity_id": request.output_entity_id,
        "x_axis_variable": request.x,
        "y_axis_variable": request.y,
    }
    match request.kind:
        case "two_by_two":
            if request.x_reference_value is None or request.y_reference_value is None:
                msg = (
                    "A two-by-two table needs x_reference_value and "
                    "y_reference_value: the exposed x value and the positive y value."
                )
                raise StatisticsRefusedError([msg])
            config = EdaTwoByTwoConfig.model_validate(
                axes
                | {
                    "x_axis_reference_value": request.x_reference_value,
                    "y_axis_reference_value": request.y_reference_value,
                }
            )
            return await two_by_two(
                site_id, study_id=study_id, filters=filters, config=config
            )
        case "contingency":
            return await contingency(
                site_id,
                study_id=study_id,
                filters=filters,
                config=EdaMosaicConfig.model_validate(axes),
            )
        case "boxplot":
            return await boxplot(
                site_id,
                study_id=study_id,
                filters=filters,
                config=EdaBoxplotConfig.model_validate(
                    axes | {"overlay_variable": request.color_by}
                ),
            )
        case "trend":
            return await trend(
                site_id,
                study_id=study_id,
                filters=filters,
                config=EdaScatterplotConfig.model_validate(
                    axes | {"value_spec": "bestFitLineWithRaw"}
                ),
                axis_names=axis_names(study, request),
            )


def axis_names(study: EdaStudyDetail, request: StatisticsRequest) -> tuple[str, str]:
    """The x and y variables, by the names the study gives them."""
    names = display_names(study)
    x, y = (
        names.get((v.entity_id, v.variable_id), v.variable_id)
        for v in (request.x, request.y)
    )
    return x, y


def statistics_title(study: EdaStudyDetail, request: StatisticsRequest) -> str:
    """The test's name and the two variables, by the names the study gives them."""
    x, y = axis_names(study, request)
    match request.kind:
        case "boxplot":
            return f"{_TESTS['boxplot']} of {y} by {x}"
        case "trend":
            return f"{_TESTS['trend']} of {y} on {x}"
        case _:
            return f"{_TESTS[request.kind]} of {x} by {y}"


async def read_statistics_part(
    binding: ConversationAnalysisView,
    *,
    study: EdaStudyDetail,
    filters: Sequence[EdaFilter],
    request: StatisticsRequest,
    caption: str = "",
) -> EdaStatisticsPart:
    """One statistic on the analysis's subset, titled, as the thread shows it."""
    errors = request_errors(study, request)
    if errors:
        raise StatisticsRefusedError(errors)
    reading = await _reading(
        binding.site_id, study=study, filters=filters, request=request
    )
    return EdaStatisticsPart(
        rows=reading.rows,
        table=reading.table,
        boxes=reading.boxes,
        trend=reading.trend,
        statistic_id=request.statistic_id(),
        dataset_id=binding.dataset_id,
        analysis_id=binding.analysis_id,
        kind=request.kind,
        title=statistics_title(study, request),
        caption=caption,
    )


__all__ = [
    "StatisticsRefusedError",
    "StatisticsRequest",
    "boxplot",
    "contingency",
    "declared",
    "lineage",
    "read_statistics_part",
    "request_errors",
    "statistics_title",
    "trend",
    "two_by_two",
]
