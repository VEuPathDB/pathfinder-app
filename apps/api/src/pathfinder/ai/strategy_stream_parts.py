"""Stream parts PathFinder emits: graph, strategy, gene sets, experiments,
the ledger, the recalled memories and the scratchpad."""

from assistant_core.conversation.stream_parts.registry import (
    StreamPartRegistry,
)
from assistant_core.graph.stream_events import (
    MemoryRetrievedPayload,
    ScratchpadUpdatedPayload,
)

from pathfinder.ai.graph.stream_events import StrategyRevisionPayload
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.stream_part_payloads import (
    ControlTestResults,
    EnrichmentResultsChunk,
    GeneSet,
    GraphCleared,
    GraphSnapshot,
    StrategyLink,
    StrategyMeta,
)
from pathfinder.services.experiment.scored_comparison import ScoredComparison
from pathfinder.services.experiment.variant_comparison import VariantComparison


def register_strategy_stream_parts(registry: StreamPartRegistry) -> None:
    registry.register("data-graph-snapshot", GraphSnapshot)
    registry.register("data-graph-cleared", GraphCleared)
    registry.register("data-strategy-meta", StrategyMeta)
    registry.register("data-strategy-link", StrategyLink)
    registry.register("data-strategy-revision", StrategyRevisionPayload)
    registry.register("data-gene-set", GeneSet)
    registry.register("data-enrichment-results", EnrichmentResultsChunk)
    registry.register("data-control-test-results", ControlTestResults)
    registry.register("data-variant-comparison", VariantComparison)
    registry.register("data-scored-comparison", ScoredComparison)
    registry.register("data-ledger-update", InvestigationLedger)
    registry.register("data-memory-retrieved", MemoryRetrievedPayload)
    registry.register("data-scratchpad-updated", ScratchpadUpdatedPayload)
