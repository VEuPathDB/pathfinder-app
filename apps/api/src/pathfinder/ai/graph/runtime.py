from __future__ import annotations

from dataclasses import dataclass, field

from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from assistant_core.graph.runtime import AssistantDeps, TurnContext
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, SkipValidation
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService
from pathfinder.services.strategies.context import StrategyMutationContext

# A search is abandoned once it has failed this many times in a turn. The
# resilience layer retries below the threshold; at or above it the search is
# both reported as unavailable AND withdrawn from the tools' search_name enum,
# so the model cannot keep re-selecting something that is down upstream.
OUTAGE_GIVE_UP_THRESHOLD = 2


@dataclass
class ServiceOutageMemory:
    """Run-scoped memory of which searches have hit transient (5xx) errors this
    turn. Lets ToolResilience abandon a persistently-unavailable search instead
    of telling the model to retry it forever.

    Counts are keyed by SEARCH NAME, not by (tool, search): a 500 is a property
    of the search, so a failure seen through ``get_search_overview`` and one
    through ``set_criterion`` are the same outage and must add up.
    """

    _counts: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def record_search_failure(self, search_name: str) -> int:
        """Record one transient failure; returns the running count."""
        self._counts[search_name] = self._counts.get(search_name, 0) + 1
        return self._counts[search_name]

    def unavailable_searches(self) -> frozenset[str]:
        """Searches abandoned for the rest of this turn."""
        return frozenset(
            name
            for name, seen in self._counts.items()
            if seen >= OUTAGE_GIVE_UP_THRESHOLD
        )


@dataclass(frozen=True, kw_only=True)
class Context(TurnContext):
    strategy_session: StrategySession
    web_search_service: WebSearchService
    literature_search_service: LiteratureSearchService
    experiment_id: str | None = None


class VerificationScope(CamelModel):
    """What this turn changed, and what the user asked verification to do.

    A fresh turn leaves the counts at zero, which warrants every check.
    """

    criteria_touched: int = 0
    is_edit: bool = False
    enrichment_requested: bool = False

    def warrants_enrichment(self) -> bool:
        """Enrichment costs a background job of minutes, so an edit that
        touched one criterion is verified by its counts instead."""
        if self.enrichment_requested:
            return True
        return not (self.is_edit and self.criteria_touched <= 1)


class AgentDeps(AssistantDeps):
    tool_repetition_guard: ToolRepetitionGuard = Field(
        default_factory=build_tool_repetition_guard,
    )
    strategy_session: SkipValidation[StrategySession]
    web_search_service: SkipValidation[WebSearchService] | None = None
    literature_search_service: SkipValidation[LiteratureSearchService] | None = None
    agent_state: AgentToolState = Field(default_factory=AgentToolState)
    ledger_summary: str = ""
    service_outage: ServiceOutageMemory = Field(default_factory=ServiceOutageMemory)
    experiment_id: str | None = None
    verification_scope: VerificationScope = Field(default_factory=VerificationScope)

    def to_strategy_context(self) -> StrategyMutationContext:
        """Narrow this container down to what strategy-mutation services need."""
        return StrategyMutationContext(
            site_id=self.site_id,
            strategy_session=self.strategy_session,
            conversation_id=self.conversation_id,
            db_session_factory=self.db_session_factory,
        )
