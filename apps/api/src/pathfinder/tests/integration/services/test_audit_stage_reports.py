"""What collect and screen report on a real database: the requests each read made, and the lane messages."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb.errors import DataParsingError, WDKError

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
    PIGA,
    FakeSite,
    RecordedLane,
    carried,
    observed_requests,
    seed_thread,
)
from pathfinder.tests.integration.services._audit_stages import SCOPE, faked_site

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

PAIR_ONLY = AuditScope(
    site_id="plasmodb",
    targets=(GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA)),),
)
SUMMARY = "0 candidates in 0 genomes, 0 sampled; 1 gene target"


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    with observed_requests():
        yield faked_site(monkeypatch)


async def _stage_requests(run_id: UUID, owner: RunOwner) -> dict[str, int]:
    run = await owned_run(run_id, owner)
    return {stage.name: stage.requests for stage in run.stages.stages}


async def _genome_requests(run_id: UUID) -> dict[str, int]:
    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    return {state.organism: state.requests for state in states}


async def _collect(owner: RunOwner, lane: RecordedLane) -> UUID:
    run_id = await create_run(owner=owner, scope=SCOPE)
    await carried(
        collect.run_collect_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    return run_id


async def _screen(owner: RunOwner, lane: RecordedLane) -> UUID:
    run_id = await create_run(owner=owner, scope=PAIR_ONLY)
    await carried(
        screen.run_screen_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    return run_id


async def test_each_genome_read_is_counted_on_its_genome_and_on_collect(
    site: FakeSite,
) -> None:
    site.failures["Plasmodium relative1 X"].extend(
        [httpx.ConnectError("connection refused")] * 2
    )
    site.failures["Plasmodium relative2 X"].append(
        DataParsingError("WDK GenesByTaxon report served 10 records of a total of 12")
    )
    owner = await seed_thread()
    run_id = await _collect(owner, RecordedLane())
    genomes = await _genome_requests(run_id)
    assert (
        genomes[NF54],
        genomes["Plasmodium relative1 X"],
        genomes["Plasmodium relative2 X"],
    ) == (1, 3, 1)
    assert sum(genomes.values()) == 12
    assert await _stage_requests(run_id, owner) == {
        "collect": 13,
        "screen": 0,
        "confirm": 0,
        "tie_break": 0,
    }


async def test_a_refused_release_read_is_counted_on_collect_each_time(
    site: FakeSite,
) -> None:
    site.release_failures.extend([WDKError("no service root", status=404)] * 2)
    owner = await seed_thread()
    lane = RecordedLane()
    run_id = await _collect(owner, lane)
    assert site.release_reads == 2
    assert (await _stage_requests(run_id, owner))["collect"] == 12
    assert lane.messages[-1] == (
        "release unknown: VEuPathDB service error: no service root"
    )


async def test_the_collect_lane_says_each_pause_and_what_it_waits_for(
    site: FakeSite,
) -> None:
    site.failures["Plasmodium relative1 X"].extend(
        [httpx.ConnectError("connection refused")] * 2
    )
    lane = RecordedLane()
    await _collect(await seed_thread(), lane)
    assert lane.messages[10:] == [
        "waiting 30 s for plasmodb, 1 genome unanswered",
        "Plasmodium relative1 X: unreached (connection refused)",
        "waiting 60 s for plasmodb, 1 genome unanswered",
        "Plasmodium relative1 X: 2 genes",
    ]


async def test_each_unanswered_target_pass_is_counted_on_screen_and_reported(
    site: FakeSite,
) -> None:
    site.target_failures.extend([httpx.ConnectError("connection refused")] * 2)
    owner = await seed_thread()
    lane = RecordedLane()
    run_id = await _screen(owner, lane)
    assert (await _stage_requests(run_id, owner))["screen"] == 4
    assert len(site.uploads) == 1
    assert lane.messages == [
        "plasmodb: gene targets unreached (connection refused)",
        "waiting 30 s for plasmodb, gene targets unanswered",
        "plasmodb: gene targets unreached (connection refused)",
        "waiting 60 s for plasmodb, gene targets unanswered",
        SUMMARY,
    ]


async def test_a_refused_target_read_reports_its_reason(site: FakeSite) -> None:
    site.target_failures.append(WDKError("bad locus tag", status=422))
    owner = await seed_thread()
    lane = RecordedLane()
    run_id = await _screen(owner, lane)
    async with async_session_factory() as session:
        (finding,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter()
        )
    assert (finding.genome, finding.status, finding.message) == ("", "screened", None)
    assert (await _stage_requests(run_id, owner))["screen"] == 2
    assert lane.messages == [
        "plasmodb: gene targets failed (VEuPathDB service error: bad locus tag)",
        SUMMARY,
    ]
