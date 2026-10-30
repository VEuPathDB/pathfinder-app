"""What an audit tool reads of its turn, and the reads, facts and records it leaves there."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.runtime import AssistantDeps
from pydantic import Field, SkipValidation
from pydantic_ai.toolsets import AbstractToolset

from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.domain.audit.verdicts import GeneModelVerdict, VerdictOrigin
from pathfinder.domain.read_facts import read_fact
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.audit.held_organisms import HeldOrganisms
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
    runs: list[UUID] = Field(default_factory=list)
    gene_genomes: dict[str, frozenset[str]] = Field(default_factory=dict)
    record_genomes: dict[str, str] = Field(default_factory=dict)
    organisms: SkipValidation[HeldOrganisms] = Field(default_factory=HeldOrganisms)

    def hold_genomes(self, genomes: Mapping[str, Iterable[str]]) -> None:
        for gene, named in genomes.items():
            held = self.gene_genomes.setdefault(gene, frozenset())
            self.gene_genomes[gene] = held | frozenset(named)

    def misplaced_genome(self, verdict: GeneModelVerdict) -> str | None:
        unread = [gene for gene in verdict.genes if gene not in self.gene_genomes]
        if unread:
            return f"no read of this turn names the genome of {', '.join(unread)}"
        named = sorted({g for gene in verdict.genes for g in self.gene_genomes[gene]})
        if verdict.model_genome in named:
            return None
        return (
            f"{verdict.model_genome} is not the genome of {', '.join(verdict.genes)}, "
            f"which the reads place in {', '.join(named)}"
        )

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
            reads=[read_fact(fact) for fact in self.facts],
            sources=[record.source_fact() for record in self.records],
            request_messages=[request] if request else [],
        )
