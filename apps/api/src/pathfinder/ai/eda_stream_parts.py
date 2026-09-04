"""Stream parts of the EDA surface: the analysis, the subset, the plot."""

from assistant_core.conversation.stream_parts.registry import StreamPartRegistry

from pathfinder.domain.eda_parts import (
    EdaAnalysisState,
    EdaSubsetPreviewPart,
    EdaVizPart,
)


def register_eda_stream_parts(registry: StreamPartRegistry) -> None:
    registry.register("data-eda.analysis-state", EdaAnalysisState)
    registry.register("data-eda.subset-preview", EdaSubsetPreviewPart)
    registry.register("data-eda.viz", EdaVizPart)
