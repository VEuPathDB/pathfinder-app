"""The chunks the EDA tools attach to their return metadata."""

from __future__ import annotations

from pydantic import TypeAdapter
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.domain.eda_parts import (
    EdaAnalysisState,
    EdaComparison,
    EdaEffectDirection,
    EdaEntityCount,
    EdaSubsetPreviewPart,
    EdaVizPart,
    EdaVolcanoPoint,
)
from pathfinder.domain.eda_thread import EdaAnalysisFacts
from pathfinder.services.eda.authoring import SubsetPreview, distribution_series
from pathfinder.services.eda.compute import RetainedSummary

_MAX_VIZ_POINTS = 4000

# A direction the chart cannot draw is refused here, not rendered wrong.
_EFFECT_DIRECTION: TypeAdapter[EdaEffectDirection] = TypeAdapter(EdaEffectDirection)


def eda_analysis_state_chunk(state: EdaAnalysisState) -> DataChunk:
    """Put the analysis state the tab also reads onto the thread.

    The id is the analysis id, so repeats inside one message reconcile to
    one part.
    """
    return DataChunk(
        type="data-eda.analysis-state",
        id=state.analysis_id,
        data=state.model_dump(by_alias=True, mode="json"),
    )


def analysis_state_chunks_if_changed(
    state: EdaAnalysisState,
    *,
    domain: StrategyDomainState,
) -> list[DataChunk]:
    """The state card, or nothing when the thread already shows this state.

    The card restates the whole analysis, so a state that reads the same adds
    no information.
    """
    facts = EdaAnalysisFacts.model_validate(state, from_attributes=True)
    if domain.eda_analysis == facts:
        return []
    domain.eda_analysis = facts
    return [eda_analysis_state_chunk(state)]


def eda_subset_preview_chunk(
    *,
    dataset_id: str,
    analysis_id: str,
    preview: SubsetPreview,
    variable_id: str | None,
    variable_display_name: str,
    is_multi_valued: bool,
    caption: str = "",
) -> DataChunk:
    """The subset's size and one variable's shape under it."""
    payload = EdaSubsetPreviewPart(
        dataset_id=dataset_id,
        analysis_id=analysis_id,
        entity_counts=[
            EdaEntityCount(
                entity_id=preview.entity_id,
                entity_display_name=preview.entity_display_name,
                count=preview.count,
                unfiltered_count=preview.unfiltered_count,
            )
        ],
        distribution=distribution_series(
            preview.distribution,
            variable_id=variable_id,
            variable_display_name=variable_display_name,
            is_multi_valued=is_multi_valued,
        ),
        distribution_note=preview.distribution_note,
        caption=caption,
    )
    return DataChunk(
        type="data-eda.subset-preview",
        data=payload.model_dump(by_alias=True, mode="json"),
    )


def eda_viz_chunk(
    *,
    dataset_id: str,
    analysis_id: str,
    effect_size_label: str,
    effect_size_threshold: float,
    significance_threshold: float,
    effect_direction: str,
    summary: RetainedSummary,
    points: list[EdaVolcanoPoint],
    retained_point_ids: list[str],
    comparison: EdaComparison,
    caption: str = "",
) -> DataChunk:
    """The volcano, capped so one message does not carry every gene.

    The retained ids are the export, so they are never capped.
    """
    ordered = sorted(points, key=lambda point: not point.retained)
    payload = EdaVizPart(
        dataset_id=dataset_id,
        analysis_id=analysis_id,
        chart="volcano",
        effect_size_label=effect_size_label,
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
        effect_direction=_EFFECT_DIRECTION.validate_python(effect_direction),
        total_points=summary.total_rows,
        retained_points=summary.retained,
        points=ordered[:_MAX_VIZ_POINTS],
        retained_point_ids=retained_point_ids,
        caption=caption,
        comparison=comparison,
    )
    return DataChunk(
        type="data-eda.viz",
        data=payload.model_dump(by_alias=True, mode="json"),
    )
