"""Gene targets and the site release on a real database: unanswered reads, named targets."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import GeneRow

from pathfinder.domain.audit.scope import (
    AuditScope,
    GenePairTarget,
    SingleGeneTarget,
)
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
    PIGA,
    FakeSite,
    RecordedLane,
    carried,
    gene_row,
    observed_requests,
    relative_organisms,
    relatives,
    seed_thread,
)
from pathfinder.tests.integration.services._audit_stages import (
    SCOPE,
    collected,
    faked_site,
    finding_keys,
    genome_states,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    with observed_requests():
        yield faked_site(monkeypatch)


PIGA_PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
PAIR_ONLY = AuditScope(site_id="plasmodb", targets=(PIGA_PAIR,))


async def _screened_targets(owner: RunOwner, seconds: float) -> UUID:
    run_id = await create_run(owner=owner, scope=PAIR_ONLY)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=seconds,
    )
    return run_id


async def _target_findings(
    run_id: UUID,
) -> list[tuple[str, str, bool, str | None]]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    return [(f.genome, f.status, f.sampled, f.message) for f in found]


async def test_a_target_unanswered_at_the_deadline_is_stored_unreached(
    site: FakeSite,
) -> None:
    site.target_failures.append(httpx.ConnectError("connection refused"))
    run_id = await _screened_targets(await seed_thread(), seconds=10)
    assert await _target_findings(run_id) == [
        ("", "unreached", True, "connection refused")
    ]


async def test_retry_unreached_reopens_an_unanswered_target(site: FakeSite) -> None:
    site.target_failures.append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    run_id = await _screened_targets(owner, seconds=10)
    async with async_session_factory() as session:
        reopened = await AuditRepository(session).reopen_unreached(run_id)
        await session.commit()
    assert reopened == "confirm"
    assert await _target_findings(run_id) == [("", "screened", True, None)]


async def test_a_target_answered_in_a_later_pass_names_its_genome(
    site: FakeSite,
) -> None:
    site.target_failures.extend([httpx.ConnectError("connection refused")] * 2)
    run_id = await _screened_targets(await seed_thread(), seconds=3600)
    assert await _target_findings(run_id) == [(NF54, "screened", True, None)]


def _short_genes(count: int) -> list[GeneRow]:
    groups = [f"OG7_00000{20 + k}" for k in range(count)]
    return [
        *(
            gene_row(f"NF54_S{k}", NF54, 200, group=group, sequence=f"chr{k + 20}")
            for k, group in enumerate(groups)
        ),
        *(row for group in groups for row in relatives(9, 400, group=group)),
    ]


async def test_a_candidate_named_as_a_target_keeps_the_targets_flags_and_spends_no_sample(
    site: FakeSite,
) -> None:
    site.rows = _short_genes(3)
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=relative_organisms(9),
        checks=("gene_length",),
        targets=(SingleGeneTarget(check="gene_length", genes=("NF54_S0",)),),
        confirm_limit=1,
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope)
    lane = RecordedLane()
    await carried(
        screen.run_screen_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    flags = {f.target.key: (f.genome, f.sampled, f.status) for f in found}
    assert flags["gene_length:NF54_S0"] == (NF54, True, "screened")
    assert sorted(flags) == [
        "gene_length:NF54_S0",
        "gene_length:NF54_S1",
        "gene_length:NF54_S2",
    ]
    assert [f.sampled for f in found].count(True) == 2
    assert lane.messages == ["2 candidates in 1 genome, 1 sampled; 1 gene target"]


async def test_a_target_written_before_its_candidate_keeps_its_flags(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(secrets, "randbits", lambda _bits: 0)
    comparison = relative_organisms(7)
    site.rows = [row for row in _short_genes(2) if row.organism in {NF54, *comparison}]
    site.failures["Plasmodium relative6 X"].append(
        httpx.ConnectError("connection refused")
    )
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=comparison,
        checks=("gene_length",),
        targets=(SingleGeneTarget(check="gene_length", genes=("NF54_S0",)),),
        confirm_limit=1,
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope, seconds=10)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert await finding_keys(run_id) == [("gene_length:NF54_S0", True)]

    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )

    assert await finding_keys(run_id) == [
        ("gene_length:NF54_S0", True),
        ("gene_length:NF54_S1", True),
    ]


async def test_a_release_read_that_never_answers_spends_none_of_the_genome_waits(
    site: FakeSite,
) -> None:
    site.release_failures.extend([httpx.ConnectError("connection refused")] * 2)
    site.failures["Plasmodium relative1 X"].extend(
        [httpx.ConnectError("connection refused")] * 20
    )
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    lane = RecordedLane()
    pauses = await carried(
        collect.run_collect_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    assert pauses == [30, 60, 120, 240, 480, 900, 900]
    assert site.genome_reads.count("Plasmodium relative1 X") == 8
    assert site.release_reads == 2
    assert (await owned_run(run_id, owner)).release is None
    assert lane.messages[-1] == "release unknown: connection refused"
    assert (await genome_states(run_id))["Plasmodium relative1 X"][0] == "unreached"


async def test_a_release_unanswered_at_the_start_is_read_again_after_the_genomes(
    site: FakeSite,
) -> None:
    site.release_failures.append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    lane = RecordedLane()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await carried(
        collect.run_collect_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    assert site.release_reads == 2
    assert (await owned_run(run_id, owner)).release == "71"
    assert not [m for m in lane.messages if m.startswith("release")]
