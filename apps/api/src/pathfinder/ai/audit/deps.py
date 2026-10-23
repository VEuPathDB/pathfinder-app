"""What an audit tool reads of its turn, and the reads, facts and records it leaves there."""

from __future__ import annotations

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.runtime import AssistantDeps
from pydantic import Field

from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.domain.audit.verdicts import VerdictOrigin
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.services.audit.verdicts import AuditCaller


class AuditDeps(AssistantDeps):
    origin: VerdictOrigin = "auditor"
    reads: set[str] = Field(default_factory=set)
    facts: list[StatisticFact] = Field(default_factory=list)
    records: list[ReadRecord] = Field(default_factory=list)

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
