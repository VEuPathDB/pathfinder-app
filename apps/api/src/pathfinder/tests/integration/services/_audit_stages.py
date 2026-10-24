"""The fake site, the scope and the reads the audit stage tests share."""

from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory

from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.services.audit import collect, screen
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    P3D7,
    PIGA,
    FakeSite,
    RecordedLane,
    carried,
    gene_row,
    relative_organisms,
    relatives,
)
from pathfinder.tests._support.audit_genome_screens import no_busco_scores
from pathfinder.tests._support.audit_provenance import served_organisms

SHORT_GROUP = "OG7_0000002"
ROWS = [
    gene_row("NF54_SHORT", NF54, 200, group=SHORT_GROUP, sequence="chr2"),
    gene_row("NF54_A", NF54, 200, start=10000),
    gene_row("NF54_B", NF54, 210, start=11000),
    gene_row(NF54_PIGA, NF54, None, pseudo=True, group="OG7_0000003", sequence="chr10"),
    gene_row(PIGA, P3D7, 461, group="OG7_0000003", sequence="Pf3D7_10_v3"),
    *relatives(9, 400),
    *relatives(9, 400, group=SHORT_GROUP),
]
SCOPE = AuditScope(
    site_id="plasmodb",
    genomes=(NF54,),
    comparison=relative_organisms(9),
    checks=("gene_length", "gene_split"),
    targets=(GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA)),),
)


def faked_site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    fake = FakeSite(ROWS)
    monkeypatch.setattr(collect, "genes_of_genome", fake.genes_of_genome)
    monkeypatch.setattr(collect, "genome_priorities", no_busco_scores)
    monkeypatch.setattr(collect, "organism_report", served_organisms)
    monkeypatch.setattr(collect, "site_build", fake.site_build)
    monkeypatch.setattr(screen, "read_gene_list", fake.read_list)
    return fake


async def collected(
    owner: RunOwner, scope: AuditScope = SCOPE, seconds: float = 3600
) -> UUID:
    run_id = await create_run(owner=owner, scope=scope)
    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=seconds,
    )
    return run_id


async def genome_states(run_id: UUID) -> dict[str, tuple[str, int, int, str | None]]:
    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    return {s.organism: (s.status, s.gene_count, s.attempts, s.message) for s in states}


async def finding_keys(run_id: UUID) -> list[tuple[str, bool]]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    return [(f.target.key, f.sampled) for f in found]
