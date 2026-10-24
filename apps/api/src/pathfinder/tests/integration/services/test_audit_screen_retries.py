"""A screen run again after a retry or a wait: it knows a genome by the genome that screened its
findings, and keeps the candidates it already wrote."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import GeneRow

from pathfinder.domain.audit.scope import AuditScope, GenePairTarget, ScreenedCheck
from pathfinder.domain.audit.screen import Candidate, screen_genomes
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_weighings import AuditWeighingRepository
from pathfinder.services.audit import collect, screen
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    P3D7,
    PIGA,
    FakeSite,
    RecordedLane,
    StageBody,
    carried,
    gene_row,
    observed_requests,
    relative_organisms,
    relatives,
    seed_thread,
)
from pathfinder.tests.integration.services._audit_stages import faked_site

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

P3D7_GROUP = "OG7_0000009"


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    with observed_requests():
        fake = faked_site(monkeypatch)
        fake.rows = [
            *fake.rows,
            gene_row("P3D7_SHORT", P3D7, 200, group=P3D7_GROUP),
            *relatives(9, 400, group=P3D7_GROUP),
        ]
        yield fake


async def _stage(
    body: StageBody, run_id: UUID, owner: RunOwner, seconds: float = 3600
) -> None:
    await carried(body, await owned_run(run_id, owner), RecordedLane(), seconds=seconds)


async def _keys(run_id: UUID) -> list[tuple[str, str]]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    return sorted((f.screened_genome, f.target.key) for f in found)


async def test_a_genome_an_error_moved_to_is_still_screened_after_a_retry(
    site: FakeSite,
) -> None:
    site.failures[P3D7].append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54, P3D7),
        comparison=relative_organisms(9),
        checks=("gene_length",),
    )
    run_id = await create_run(owner=owner, scope=scope)
    await _stage(collect.run_collect_stage, run_id, owner, seconds=10)
    await _stage(screen.run_screen_stage, run_id, owner)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        (short,) = await repo.findings(run_id, FindingFilter())
        await repo.try_finding(short.id)
        await repo.settle_finding(
            short.id,
            SettledFinding(
                status="confirmed", error_type="truncated_model", certainty="high"
            ),
        )
        await AuditWeighingRepository(session).remodel(
            short.id, "over_extended_model", "medium", P3D7
        )
        assert await AuditRepository(session).reopen_unreached(run_id) == "collect"
        await session.commit()

    await _stage(collect.run_collect_stage, run_id, owner)
    await _stage(screen.run_screen_stage, run_id, owner)

    assert await _keys(run_id) == [
        (P3D7, "gene_length:P3D7_SHORT"),
        (NF54, "gene_length:NF54_SHORT"),
    ]


async def test_a_wait_for_the_gene_targets_keeps_the_screened_candidates(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    screened: list[str] = []

    def counted(
        checks: tuple[ScreenedCheck, ...],
        audited: Mapping[str, list[GeneRow]],
        comparison: Sequence[GeneRow],
    ) -> list[Candidate]:
        screened.extend(audited)
        return screen_genomes(checks, audited, comparison)

    monkeypatch.setattr(screen, "screen_genomes", counted)
    site.target_failures.append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    pair = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=relative_organisms(9),
        checks=("gene_length",),
        targets=(pair,),
    )
    run_id = await create_run(owner=owner, scope=scope)
    await _stage(collect.run_collect_stage, run_id, owner)
    await _stage(screen.run_screen_stage, run_id, owner)

    assert screened == [NF54]
    assert await _keys(run_id) == [
        (NF54, "gene_length:NF54_SHORT"),
        (NF54, pair.key),
    ]
