"""Collect and screen on a real database: stored genomes, waited-for reads, written candidates."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import DataParsingError
from veupathdb_mcp.audit import GeneRow

from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit import collect, screen
from pathfinder.services.audit.progress import RunLanes
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
    observed_requests,
    relative_organisms,
    relatives,
    seed_thread,
)
from pathfinder.tests.integration.services._audit_stages import (
    SCOPE,
    SHORT_GROUP,
    collected,
    faked_site,
    finding_keys,
    genome_states,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

RESEARCHER_TOKEN = "researcher-wdk-token"


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    with observed_requests():
        yield faked_site(monkeypatch)


async def test_collect_stores_every_genome_and_the_release(site: FakeSite) -> None:
    owner = await seed_thread()
    run_id = await collected(owner)
    states = await genome_states(run_id)
    assert (await owned_run(run_id, owner)).release == "71"
    assert states[NF54] == ("collected", 4, 1, None)
    assert states["Plasmodium relative0 X"] == ("collected", 2, 1, None)
    assert len(states) == 10


async def test_the_stages_read_under_the_token_the_run_carries(
    site: FakeSite,
) -> None:
    owner = await seed_thread()
    held = veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
    try:
        run_id = await collected(owner)
        await carried(
            screen.run_screen_stage,
            await owned_run(run_id, owner),
            RecordedLane(),
            seconds=3600,
        )
    finally:
        veupathdb_auth_token_ctx.reset(held)
    assert site.tokens == {RESEARCHER_TOKEN}
    assert len(site.genome_reads) == 10


async def test_an_unanswered_genome_is_read_again_in_a_later_pass(
    site: FakeSite,
) -> None:
    site.failures["Plasmodium relative1 X"].extend(
        [httpx.ConnectError("connection refused")] * 2
    )
    owner = await seed_thread()
    states = await genome_states(await collected(owner))
    assert states["Plasmodium relative1 X"] == ("collected", 2, 3, None)
    assert site.genome_reads.count("Plasmodium relative1 X") == 3


async def test_a_truncated_genome_report_raised_as_a_parse_failure_fails_after_one_read(
    site: FakeSite,
) -> None:
    site.failures["Plasmodium relative2 X"].append(
        DataParsingError("WDK GenesByTaxon report served 10 records of a total of 12")
    )
    owner = await seed_thread()
    states = await genome_states(await collected(owner))
    assert states["Plasmodium relative2 X"] == (
        "failed",
        0,
        1,
        "Data parsing failed: WDK GenesByTaxon report served 10 records of a total of 12",
    )
    assert site.genome_reads.count("Plasmodium relative2 X") == 1


async def test_a_genome_still_unanswered_at_the_deadline_is_stored_unreached_and_read_next_time(
    site: FakeSite,
) -> None:
    site.failures["Plasmodium relative3 X"].append(httpx.ConnectError("refused"))
    owner = await seed_thread()
    run_id = await collected(owner, seconds=10)
    assert (await genome_states(run_id))["Plasmodium relative3 X"][0] == "unreached"
    reads = len(site.genome_reads)
    await carried(
        collect.run_collect_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert site.genome_reads[reads:] == ["Plasmodium relative3 X"]
    assert (await genome_states(run_id))["Plasmodium relative3 X"][0] == "collected"


async def test_screen_writes_the_split_the_short_gene_and_the_target(
    site: FakeSite,
) -> None:
    owner = await seed_thread()
    run_id = await collected(owner)
    lane = RecordedLane()
    await carried(
        screen.run_screen_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    assert [(f.target.key, f.genome, f.sampled, f.status) for f in found] == [
        ("gene_split:NF54_A+NF54_B", NF54, True, "screened"),
        ("gene_length:NF54_SHORT", NF54, True, "screened"),
        (f"pseudogene_call:{NF54_PIGA}+{PIGA}", NF54, True, "screened"),
    ]
    assert lane.messages == ["2 candidates in 1 genome, 2 sampled; 1 gene target"]


async def test_a_target_the_site_names_under_another_id_is_kept_without_a_genome(
    site: FakeSite,
) -> None:
    scope = AuditScope(
        site_id="plasmodb",
        targets=(
            GenePairTarget(
                check="pseudogene_call", genes=("PfNF54_100037200:pseudogene", PIGA)
            ),
        ),
    )
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=scope)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    async with async_session_factory() as session:
        (finding,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter()
        )
    assert (finding.genome, finding.status) == ("", "screened")


async def test_candidates_past_the_limit_are_stored_unsampled(site: FakeSite) -> None:
    groups = ("OG7_0000011", "OG7_0000012", "OG7_0000013")
    site.rows = [
        *(
            gene_row(f"NF54_S{k}", NF54, 200, group=group, sequence=f"chr{k + 20}")
            for k, group in enumerate(groups)
        ),
        *(row for group in groups for row in relatives(9, 400, group=group)),
    ]
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=relative_organisms(9),
        checks=("gene_length",),
        confirm_limit=1,
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    assert sorted(f.target.genes[0] for f in found) == ["NF54_S0", "NF54_S1", "NF54_S2"]
    assert sorted(f.status for f in found) == ["screened", "unsampled", "unsampled"]
    assert [f.sampled for f in found].count(True) == 1


async def test_a_screen_run_again_keeps_each_screened_genomes_first_sample(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()
    run_id = await collected(owner)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    first = await finding_keys(run_id)
    reads: list[str] = []
    stored = AuditRepository.collected_genome

    async def reading(repo: AuditRepository, run: UUID, organism: str) -> list[GeneRow]:
        reads.append(organism)
        return await stored(repo, run, organism)

    monkeypatch.setattr(AuditRepository, "collected_genome", reading)
    lane = RecordedLane()
    await carried(
        screen.run_screen_stage, await owned_run(run_id, owner), lane, seconds=3600
    )
    assert await finding_keys(run_id) == first
    assert reads == []
    assert lane.messages == ["0 candidates in 0 genomes, 0 sampled; 0 gene targets"]


async def test_a_genome_screened_with_no_candidate_is_screened_again_after_a_late_genome(
    site: FakeSite,
) -> None:
    site.rows = [
        gene_row("NF54_SHORT", NF54, 200, group=SHORT_GROUP, sequence="chr2"),
        *relatives(7, 400, group=SHORT_GROUP),
    ]
    site.failures["Plasmodium relative6 X"].append(
        httpx.ConnectError("connection refused")
    )
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=relative_organisms(7),
        checks=("gene_length",),
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope, seconds=10)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert await finding_keys(run_id) == []

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

    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    assert [(f.target.key, f.sampled, f.status) for f in found] == [
        ("gene_length:NF54_SHORT", True, "screened")
    ]


LATE_GROUPS = ("OG7_0000031", "OG7_0000032")


@pytest.mark.parametrize("late", [P3D7, NF54])
async def test_a_genome_screened_late_is_judged_with_the_screened_genomes_rows(
    site: FakeSite, late: str
) -> None:
    first, second = LATE_GROUPS
    site.rows = [
        gene_row("NF54_X", NF54, 200, group=first, sequence="chr31"),
        gene_row("NF54_Y", NF54, 400, group=second, sequence="chr32"),
        gene_row("3D7_Y", P3D7, 200, group=second, sequence="Pf3D7_32_v3"),
        *relatives(7, 400, group=first),
        *relatives(6, 400, group=second),
    ]
    site.failures[late].append(httpx.ConnectError("connection refused"))
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54, P3D7),
        comparison=relative_organisms(7),
        checks=("gene_length",),
    )
    owner = await seed_thread()
    run_id = await collected(owner, scope, seconds=10)
    for stage in (screen.run_screen_stage, collect.run_collect_stage):
        await carried(
            stage, await owned_run(run_id, owner), RecordedLane(), seconds=3600
        )
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    assert sorted(await finding_keys(run_id)) == [
        ("gene_length:3D7_Y", True),
        ("gene_length:NF54_X", True),
    ]


async def test_a_run_is_resumed_only_by_its_own_thread() -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    assert (await owned_run(run_id, owner)).id == run_id
    with pytest.raises(NotFoundError):
        await owned_run(
            run_id, RunOwner(user_id=owner.user_id, conversation_id=uuid4())
        )
    with pytest.raises(NotFoundError):
        await owned_run(
            run_id, RunOwner(user_id=uuid4(), conversation_id=owner.conversation_id)
        )


async def test_each_stage_reports_on_its_run() -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    lanes = RunLanes(await owned_run(run_id, owner))
    await lanes.lane("collect").update(done=1, total=4, message="NF54: 4 genes")
    await lanes.lane("screen").update(done=0, total=0, message="nothing to screen")
    await lanes.lane("collect").update(done=4, total=4, message="relative: 2 genes")
    await lanes.waiting("plasmodb")
    waited = (await owned_run(run_id, owner)).stages.stages[0].message
    await lanes.running("plasmodb")
    await lanes.say("confirm", "sign-in needed")
    stages = (await owned_run(run_id, owner)).stages.stages
    assert waited == "Waiting for PlasmoDB"
    assert [(s.name, s.done, s.total, s.message) for s in stages] == [
        ("collect", 4, 4, "relative: 2 genes"),
        ("screen", 0, 0, "nothing to screen"),
        ("confirm", 0, 0, "sign-in needed"),
        ("tie_break", 0, 0, ""),
    ]
    resumed = RunLanes(await owned_run(run_id, owner))
    await resumed.say("collect", "sign-in needed")
    (collect_stage, *_) = (await owned_run(run_id, owner)).stages.stages
    assert (collect_stage.done, collect_stage.total) == (4, 4)
