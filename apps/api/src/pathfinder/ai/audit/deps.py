"""What an audit tool reads of its turn, and the reads, facts and records it leaves there."""

from __future__ import annotations

from typing import Any

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.runtime import AssistantDeps
from pydantic import Field, SkipValidation
from pydantic_ai.toolsets import AbstractToolset

from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.domain.audit.verdicts import VerdictOrigin
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.audit.verdicts import AuditCaller

FINDINGS_PER_CALL = 25


class AuditDeps(AssistantDeps):
    origin: VerdictOrigin = "auditor"
    tool_sources: SkipValidation[AbstractToolset[Any]] | None = None
    request: str = ""
    reply_refusals: int = 0
    reads: set[str] = Field(default_factory=set)
    facts: list[StatisticFact] = Field(default_factory=list)
    records: list[ReadRecord] = Field(default_factory=list)
    recorded: list[int] = Field(default_factory=list)

    @property
    def caller(self) -> AuditCaller:
        if self.user_id is None:
            msg = "An audit is read and started only by a signed-in researcher."
            raise CallRefused(msg)
        return AuditCaller(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            site_id=self.site_id,
        )

    def held_reads(self) -> frozenset[str]:
        return frozenset(self.reads)

    def turn_facts(self, request: str) -> TurnFacts:
        return TurnFacts(
            statistics=list(self.facts),
            sources=[record.source_fact() for record in self.records],
            request_messages=[request] if request else [],
        )
