"""Stream parts Strategist emits: graph, strategy, gene sets, control tests,
comparisons, the evidence card, a separation run's result, a delete card's
cascade, the ledger, the route a turn took, the facts beside a reply, the links a reply may show, the
recalled memories and this assistant's agent topology, and the proposal a card
carries as its tool input."""

from assistant_core.conversation.stream_parts.agent_topology import (
    register_agent_topology_stream_parts,
)
from assistant_core.conversation.stream_parts.registry import (
    StreamPartRegistry,
)

from pathfinder.ai.graph.stream_events import (
    BuildOfferPayload,
    DeleteCascadePayload,
    RecalledMemoriesPayload,
    StrategyRevisionPayload,
    TurnRoutePayload,
)
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.proposal import Proposal
from pathfinder.ai.stream_part_payloads import (
    ControlTestResults,
    GeneSet,
    GraphCleared,
    GraphSnapshot,
    ListedGeneSets,
    StrategyLink,
    StrategyMeta,
)
from pathfinder.domain.evidence import EvidenceCard
from pathfinder.domain.reply_links import ReplyLinks
from pathfinder.domain.separation import SeparationReport
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.experiment.column_tally import ColumnTally
from pathfinder.services.experiment.scored_comparison import ScoredComparison
from pathfinder.services.experiment.variant_comparison import VariantComparison


def register_strategy_stream_parts(registry: StreamPartRegistry) -> None:
    registry.register("data-graph-snapshot", GraphSnapshot)
    registry.register("data-graph-cleared", GraphCleared)
    registry.register("data-strategy-meta", StrategyMeta)
    registry.register("data-strategy-link", StrategyLink)
    registry.register("data-strategy-revision", StrategyRevisionPayload)
    registry.register("data-gene-set", GeneSet)
    registry.register("data-gene-set-list", ListedGeneSets)
    registry.register("data-control-test-results", ControlTestResults)
    registry.register("data-evidence-card", EvidenceCard)
    registry.register("data-separation-result", SeparationReport)
    registry.register("data-variant-comparison", VariantComparison)
    registry.register("data-column-tally", ColumnTally)
    registry.register("data-scored-comparison", ScoredComparison)
    registry.register("data-ledger-update", InvestigationLedger)
    registry.register("data-facts", TurnFacts)
    registry.register("data-memory-retrieved", RecalledMemoriesPayload)
    registry.register("data-delete-cascade", DeleteCascadePayload)
    registry.register("data-turn-route", TurnRoutePayload)
    registry.register("data-reply-links", ReplyLinks)
    registry.register("data-build-offer", BuildOfferPayload)
    registry.register_schema_only("proposal", Proposal)
    register_agent_topology_stream_parts(registry)
