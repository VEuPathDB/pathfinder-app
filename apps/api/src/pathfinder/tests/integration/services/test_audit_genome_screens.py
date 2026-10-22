"""A genome's pseudogene calls screened against a reference genome, and each genome's stored BUSCO gap."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb import get_observer
from veupathdb.errors import DataParsingError
from veupathdb_mcp.audit import GenomePriority

from pathfinder.domain.audit.scope import AuditScope
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.services.audit import collect, screen
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.tests._support.audit import (
    NF54,
    P3D7,
    FakeSite,
    RecordedLane,
    carried,
    gene_row,
    observed_requests,
    relative_organisms,
    relatives,
    seed_thread,
)
from pathfinder.tests._support.audit_genome_screens import (
    NF54_PIGA_PSEUDOGENE,
    NF54_PIGA_ROW,
    NF135,
    NF135_PRIORITY,
    P3D7_PIGA_ROW,
)
from pathfinder.tests.integration.services._audit_stages import (
    SHORT_GROUP,
    collected,
    faked_site,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

PIGA_CALL = f"pseudogene_call:{NF54_PIGA_PSEUDOGENE.replace(':', '%3A')}+PF3D7_1032400"
FAMILY_ROW = NF54_PIGA_ROW.model_copy(
    update={"gene": "PfNF54_RIF:pseudogene", "product": "rifin, pseudogene"}
)
CALLS = AuditScope(
    site_id="plasmodb",
    genomes=(NF54,),
    comparison=(P3D7,),
    checks=("pseudogene_call",),
    reference_genome=P3D7,
)
RELATIVE = "Plasmodium relative0 X"
_NF135_ONLY = AuditScope(site_id="plasmodb", genomes=(NF135,), checks=("gene_length",))
_REQUEST = {
    "method": "POST",
    "endpoint_group": "records",
    "site_host": "qa.plasmodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}


class Scores:
    def __init__(self, served: list[GenomePriority]) -> None:
        self.served = served
        self.failures: list[BaseException] = []
        self.reads = 0

    async def genome_priorities(self, site_id: str) -> list[GenomePriority]:
        del site_id
        self.reads += 1
        get_observer().on_wdk_request(0.01, _REQUEST)
        if self.failures:
            raise self.failures.pop(0)
        return self.served


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    with observed_requests():
        yield faked_site(monkeypatch)


@pytest.fixture
def scores(monkeypatch: pytest.MonkeyPatch) -> Scores:
    served = Scores([NF135_PRIORITY])
    monkeypatch.setattr(collect, "genome_priorities", served.genome_priorities)
    return served


async def _screened(run_id: UUID, owner: RunOwner, lane: RecordedLane) -> None:
    await carried(
        screen.run_screen_stage, await owned_run(run_id, owner), lane, seconds=3600
    )


async def _findings(run_id: UUID) -> list[tuple[str, str, bool, str]]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    return [(f.target.key, f.genome, f.sampled, f.status) for f in found]


async def _requests(run_id: UUID, owner: RunOwner) -> dict[str, int]:
    run = await owned_run(run_id, owner)
    return {stage.name: stage.requests for stage in run.stages.stages}


async def _states(run_id: UUID) -> dict[str, tuple[str, float | None, int, str | None]]:
    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    return {
        s.organism: (
            s.status,
            None if s.priority is None else s.priority.gap,
            s.attempts,
            s.message,
        )
        for s in states
    }


async def _genome_requests(run_id: UUID) -> dict[str, int]:
    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    return {s.organism: s.requests for s in states}


async def test_a_pseudogene_call_is_screened_from_the_two_collected_genomes(
    site: FakeSite,
) -> None:
    site.rows = [NF54_PIGA_ROW, FAMILY_ROW, P3D7_PIGA_ROW]
    owner = await seed_thread()
    run_id = await collected(owner, CALLS)
    lane = RecordedLane()
    await _screened(run_id, owner, lane)
    assert await _findings(run_id) == [(PIGA_CALL, NF54, True, "screened")]
    assert lane.messages == ["1 candidate in 1 genome, 1 sampled; 0 gene targets"]
    assert site.genome_reads == [NF54, P3D7]
    assert (await _requests(run_id, owner))["screen"] == 0


async def test_a_paired_genome_is_not_paired_again(site: FakeSite) -> None:
    site.rows = [NF54_PIGA_ROW, P3D7_PIGA_ROW]
    owner = await seed_thread()
    run_id = await collected(owner, CALLS)
    await _screened(run_id, owner, RecordedLane())
    again = RecordedLane()
    await _screened(run_id, owner, again)
    assert await _findings(run_id) == [(PIGA_CALL, NF54, True, "screened")]
    assert again.messages == ["0 candidates in 0 genomes, 0 sampled; 0 gene targets"]


async def test_a_genome_screened_before_its_reference_genome_is_paired_once_it_is(
    site: FakeSite,
) -> None:
    site.rows = [
        NF54_PIGA_ROW,
        P3D7_PIGA_ROW,
        gene_row("NF54_SHORT", NF54, 200, group=SHORT_GROUP, sequence="chr2"),
        *relatives(7, 400, group=SHORT_GROUP),
    ]
    site.failures[P3D7].append(httpx.ConnectError("connection refused"))
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=(*relative_organisms(7), P3D7),
        checks=("gene_length", "pseudogene_call"),
        reference_genome=P3D7,
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope, seconds=10)
    first = RecordedLane()
    await _screened(run_id, owner, first)
    assert await _findings(run_id) == [
        ("gene_length:NF54_SHORT", NF54, True, "screened")
    ]
    assert first.messages == [
        (
            "1 candidate in 1 genome, 1 sampled; 0 gene targets; "
            f"reference genome {P3D7} not collected"
        )
    ]

    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.finish_stage(run_id, "collect")
        await repo.finish_stage(run_id, "screen")
        assert await repo.reopen_unreached(run_id) == "collect"
        await session.commit()
    reopened = await owned_run(run_id, owner)
    assert reopened.stages.unfinished == ("collect", "screen", "confirm", "tie_break")
    await carried(collect.run_collect_stage, reopened, RecordedLane(), seconds=3600)
    await _screened(run_id, owner, RecordedLane())
    await _screened(run_id, owner, RecordedLane())

    assert await _findings(run_id) == [
        ("gene_length:NF54_SHORT", NF54, True, "screened"),
        (PIGA_CALL, NF54, True, "screened"),
    ]


async def test_collect_stores_each_audited_genomes_gap_from_one_report_read(
    site: FakeSite, scores: Scores
) -> None:
    scores.served = [
        NF135_PRIORITY,
        NF135_PRIORITY.model_copy(update={"organism": RELATIVE}),
    ]
    site.rows = [*site.rows, gene_row("NF135_A", NF135, 300)]
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF135, NF54),
        comparison=relative_organisms(9),
        checks=("gene_length",),
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope)
    states = await _states(run_id)
    assert (states[NF135], states[NF54], states[RELATIVE]) == (
        ("collected", 5.4, 1, None),
        ("collected", None, 1, None),
        ("collected", None, 1, None),
    )
    assert scores.reads == 1
    assert (await _genome_requests(run_id))[NF135] == 2
    assert (await _requests(run_id, owner))["collect"] == len(site.genome_reads) + 2


async def test_an_unanswered_score_read_leaves_the_genomes_unreached_until_a_later_pass(
    site: FakeSite, scores: Scores
) -> None:
    site.rows = [gene_row("NF135_A", NF135, 300), gene_row("NF54_A", NF54, 300)]
    scores.failures.append(httpx.ConnectError("connection refused"))
    scope = AuditScope(
        site_id="plasmodb", genomes=(NF135, NF54), checks=("gene_length",)
    )
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=scope)
    lane = RecordedLane()
    await carried(
        collect.run_collect_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    states = await _states(run_id)
    assert (states[NF135], states[NF54]) == (
        ("collected", 5.4, 2, None),
        ("collected", None, 2, None),
    )
    assert scores.reads == 2
    assert site.genome_reads == [NF135, NF54]
    assert lane.messages[:3] == [
        f"{NF135}: unreached (BUSCO scores unreached: connection refused)",
        f"{NF54}: unreached (BUSCO scores unreached: connection refused)",
        "waiting 30 s for plasmodb, 2 genomes unanswered",
    ]


async def test_a_score_read_the_deadline_cut_off_is_listed_and_retried(
    site: FakeSite, scores: Scores
) -> None:
    del site
    scores.failures.append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=_NF135_ONLY)
    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=10,
    )
    assert (await _states(run_id))[NF135] == (
        "unreached",
        None,
        1,
        "BUSCO scores unreached: connection refused",
    )
    async with async_session_factory() as session:
        assert await AuditRepository(session).reopen_unreached(run_id) == "collect"
        await session.commit()

    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert (await _states(run_id))[NF135] == ("collected", 5.4, 2, None)
    assert scores.reads == 2


async def test_a_stored_score_is_never_read_again(
    site: FakeSite, scores: Scores
) -> None:
    site.failures[NF135].append(httpx.ConnectError("connection refused"))
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=_NF135_ONLY)
    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert (await _states(run_id))[NF135] == ("collected", 5.4, 2, None)
    assert (scores.reads, site.genome_reads) == (1, [NF135, NF135])


async def test_an_unreadable_score_report_settles_the_genome_collected_without_a_gap(
    site: FakeSite, scores: Scores
) -> None:
    scores.failures.append(
        DataParsingError("the organism report served unreadable BUSCO scores")
    )
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=_NF135_ONLY)
    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert (await _states(run_id))[NF135] == (
        "collected",
        None,
        1,
        (
            "BUSCO scores failed: Data parsing failed: "
            "the organism report served unreadable BUSCO scores"
        ),
    )
    assert (scores.reads, site.genome_reads) == (1, [NF135])
