"""Stream parts PathFinder emits: graph, strategy, gene sets, control tests,
comparisons, the evidence card, the ledger, the recalled memories and this
assistant's agent topology, and the proposal a card carries as its tool input."""

from assistant_core.conversation.stream_parts.agent_topology import (
    register_agent_topology_stream_parts,
)
from assistant_core.conversation.stream_parts.registry import (
    StreamPartRegistry,
)
from assistant_core.graph.stream_events import MemoryRetrievedPayload

from pathfinder.ai.graph.stream_events import StrategyRevisionPayload
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.proposal import Proposal
from pathfinder.ai.stream_part_payloads import (
    ControlTestResults,
    GeneSet,
    GraphCleared,
    GraphSnapshot,
    StrategyLink,
    StrategyMeta,
)
from pathfinder.domain.evidence import EvidenceCard
from pathfinder.services.experiment.scored_comparison import ScoredComparison
from pathfinder.services.experiment.variant_comparison import VariantComparison


def register_strategy_stream_parts(registry: StreamPartRegistry) -> None:
    registry.register("data-graph-snapshot", GraphSnapshot)
    registry.register("data-graph-cleared", GraphCleared)
    registry.register("data-strategy-meta", StrategyMeta)
    registry.register("data-strategy-link", StrategyLink)
    registry.register("data-strategy-revision", StrategyRevisionPayload)
    registry.register("data-gene-set", GeneSet)
    registry.register("data-control-test-results", ControlTestResults)
    registry.register("data-evidence-card", EvidenceCard)
    registry.register("data-variant-comparison", VariantComparison)
    registry.register("data-scored-comparison", ScoredComparison)
    registry.register("data-ledger-update", InvestigationLedger)
    registry.register("data-memory-retrieved", MemoryRetrievedPayload)
    registry.register_schema_only("proposal", Proposal)
    register_agent_topology_stream_parts(registry)
