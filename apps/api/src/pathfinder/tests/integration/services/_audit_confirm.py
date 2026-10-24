"""The fake library checks, the run and the reads the confirm and tie-break tests share."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from fastmcp.exceptions import ToolError
from veupathdb import get_observer
from veupathdb_mcp.audit import (
    GeneEvidence,
    GeneLengthAudit,
    GeneRow,
    GroupMember,
    OrthologGroup,
    PseudogeneCallAudit,
)

from pathfinder.domain.audit.findings import EvidenceKind
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget, SingleGeneTarget
from pathfinder.persistence.models import (
    AuditEvidenceRecord,
    AuditFindingRecord,
    AuditRunRecord,
)
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.services.audit import checks, confirm, tie_break, weighing
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    P3D7,
    PIGA,
    PIGA_INTACT,
    FakeSite,
    gene_row,
    not_checked_audit,
    relatives,
    seed_thread,
    short_audit,
    split_audit,
)
from pathfinder.tests._support.audit_evidence import evidence_of

SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
OTHER_SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT2",))
PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
TYPICAL = SingleGeneTarget(check="gene_length", genes=("NF54_TYPICAL",))
SPLIT = GenePairTarget(check="gene_split", genes=("NF54_B", "NF54_A"))
REFERENCE = "OG7_0000001_REL0"
OTHER_REFERENCE = "OG7_0000001_REL1"
UNANSWERED = "plasmodb did not answer the audit reads: ConnectError connection refused"
ROWS = [
    gene_row("NF54_SHORT", NF54, 200),
    gene_row("NF54_SHORT2", NF54, 190, start=50000),
    gene_row("NF54_A", NF54, 150, start=10000),
    gene_row("NF54_B", NF54, 220, start=11000),
    *(row for row in relatives(9, 400) if row.gene != OTHER_REFERENCE),
    gene_row(OTHER_REFERENCE, "Plasmodium relative1 X", 420),
    gene_row(NF54_PIGA, NF54, None, pseudo=True, group="OG7_0000003"),
    gene_row(PIGA, P3D7, 461, group="OG7_0000003"),
]
_REQUEST = {
    "method": "POST",
    "endpoint_group": "searches",
    "site_host": "qa.plasmodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}


def _requested() -> None:
    get_observer().on_wdk_request(0.01, _REQUEST)


def unanswered() -> ToolError:
    error = ToolError(UNANSWERED)
    error.__cause__ = httpx.ConnectError("connection refused")
    return error


def screened(*targets: SingleGeneTarget | GenePairTarget) -> list[NewFinding]:
    return [
        NewFinding(genome=NF54, target=t, sampled=True, status="screened")
        for t in targets
    ]


class CheckTools:
    def __init__(self) -> None:
        self.site = FakeSite(ROWS)
        self.length_failures: defaultdict[str, list[BaseException]] = defaultdict(list)
        self.pseudogene_failures: list[BaseException] = []
        self.ortholog_failures: defaultdict[str, list[BaseException]] = defaultdict(
            list
        )
        self.ortholog_reads: list[str] = []
        self.ortholog_rows: list[GeneRow] | None = None
        self.evidence_failures: defaultdict[str, list[BaseException]] = defaultdict(
            list
        )
        self.evidence_reads: list[str] = []
        self.uncited: set[str] = set()
        self.references: dict[str, str] = {}
        self.unreferenced: set[str] = set()

    async def length(self, site_id: str, gene: str) -> GeneLengthAudit:
        del site_id
        _requested()
        if self.length_failures[gene]:
            raise self.length_failures[gene].pop(0)
        if gene == "NF54_TYPICAL":
            return not_checked_audit([gene], "TYPICAL", reference_gene=REFERENCE)
        audit = short_audit(gene, reference_gene=self.references.get(gene, REFERENCE))
        if gene in self.unreferenced:
            return audit.model_copy(update={"reference_gene": None})
        return audit

    async def split(self, site_id: str, gene_a: str, gene_b: str) -> GeneLengthAudit:
        del site_id
        _requested()
        return split_audit(gene_a, gene_b, reference_gene=REFERENCE)

    async def pseudogene(
        self, site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del site_id, strain_gene, reference_gene
        _requested()
        if self.pseudogene_failures:
            raise self.pseudogene_failures.pop(0)
        return PIGA_INTACT

    async def orthologs(self, site_id: str, gene: str) -> OrthologGroup:
        del site_id
        _requested()
        self.ortholog_reads.append(gene)
        if self.ortholog_failures[gene]:
            raise self.ortholog_failures[gene].pop(0)
        rows = self.ortholog_rows or [
            row for row in ROWS if row.ortholog_group == "OG7_0000001"
        ]
        return OrthologGroup(
            gene=gene,
            members=[GroupMember.of_row(row) for row in rows if row.gene != gene],
        )

    async def evidence(self, site_id: str, gene: str) -> GeneEvidence:
        del site_id
        _requested()
        self.evidence_reads.append(gene)
        if self.evidence_failures[gene]:
            raise self.evidence_failures[gene].pop(0)
        cited = evidence_of(gene)
        if gene in self.uncited:
            return cited.model_copy(update={"pubmed": 0})
        return cited


class CountedLane:
    def __init__(self) -> None:
        self.updates: list[tuple[int, int, str]] = []

    async def update(self, *, done: int, total: int, message: str) -> None:
        self.updates.append((done, total, message))


def faked_checks(monkeypatch: pytest.MonkeyPatch) -> CheckTools:
    fakes = CheckTools()
    monkeypatch.setattr(checks, "audit_gene_length", fakes.length)
    monkeypatch.setattr(checks, "audit_pseudogene_call", fakes.pseudogene)
    monkeypatch.setattr(checks, "audit_gene_split", fakes.split)
    monkeypatch.setattr(confirm, "record_rows", fakes.site.named_rows)
    monkeypatch.setattr(tie_break, "orthologs_of", fakes.orthologs)
    monkeypatch.setattr(tie_break, "record_rows", fakes.site.named_rows)
    monkeypatch.setattr(weighing, "audit_gene_evidence", fakes.evidence)
    return fakes


async def run_with(findings: list[NewFinding]) -> AuditRunRecord:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(PAIR,))
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(run_id, findings)
        await session.commit()
    return await owned_run(run_id, owner)


async def confirmed_with_no_evidence(run_id: UUID, gene: str) -> None:
    finding = (await findings_of(run_id))[gene]
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.try_finding(finding.id)
        await repo.settle_finding(
            finding.id,
            SettledFinding(
                status="confirmed", error_type="truncated_model", certainty="high"
            ),
        )
        await session.commit()


async def findings_of(run_id: UUID) -> dict[str, AuditFindingRecord]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    return {f.target.genes[0]: f for f in found}


async def weighed_of(
    run_id: UUID, kind: EvidenceKind = "relatives"
) -> dict[str, AuditEvidenceRecord]:
    found = await findings_of(run_id)
    genes = {f.id: gene for gene, f in found.items()}
    async with async_session_factory() as session:
        weighed = await AuditFindingRepository(session).evidence(
            run_id, list(genes), kinds=(kind,)
        )
    return {genes[e.finding_id]: e for e in weighed}


async def stage_requests(run: AuditRunRecord) -> dict[str, int]:
    async with async_session_factory() as session:
        read = await AuditRepository(session).run(run.id, user_id=run.user_id)
    assert read is not None
    return {stage.name: stage.requests for stage in read.stages.stages}
