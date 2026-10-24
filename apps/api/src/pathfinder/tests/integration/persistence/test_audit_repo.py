"""The audit run rows: owned runs, stage state, resumable genomes and their purge."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from assistant_core.platform.context import application_id_ctx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import AuditEvidence, AuditFinding, AuditGenome
from pathfinder.persistence.repositories.audit import (
    STOPPED_MESSAGE,
    AuditRepository,
    CollectedGenome,
    UnitNotOpenError,
)
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
)
from pathfinder.tests._support.audit import NF54, gene_row
from pathfinder.tests._support.audit_genome_screens import NF135, NF135_PRIORITY
from pathfinder.tests.integration.persistence._audit_runs import (
    PAIR,
    RELATIVES,
    SCOPE,
    UNREACHED,
    new_owner,
    new_run,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

RELATIVE = "Plasmodium relative0 X"


async def test_a_run_is_read_only_by_its_owner_in_its_application(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)
    async with session_maker() as session:
        repo = AuditRepository(session)
        run = await repo.run(run_id, user_id=user_id)
        assert run is not None
        assert (
            run.scope,
            run.seed,
            run.status,
            run.stages.next_stage,
        ) == (
            SCOPE,
            7,
            "planned",
            "collect",
        )
        assert await repo.sealed_token(run_id) is None
        assert await repo.run(run_id, user_id=uuid4()) is None
        token = application_id_ctx.set("another-application")
        try:
            assert await repo.run(run_id, user_id=user_id) is None
            assert await repo.runs(user_id=user_id) == []
        finally:
            application_id_ctx.reset(token)


async def test_runs_list_the_owners_runs_newest_first(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user_id, conversation_id = await new_owner(session)
        other_user, other_conversation = await new_owner(session)
        first = await AuditRepository(session).create_run(
            user_id=user_id, conversation_id=conversation_id, scope=SCOPE, seed=7
        )
        await session.commit()
    async with session_maker() as session:
        repo = AuditRepository(session)
        second = await repo.create_run(
            user_id=user_id, conversation_id=conversation_id, scope=SCOPE, seed=8
        )
        await repo.create_run(
            user_id=other_user, conversation_id=other_conversation, scope=SCOPE, seed=9
        )
        await session.commit()
    async with session_maker() as session:
        runs = await AuditRepository(session).runs(user_id=user_id)
    assert [(r.id, r.seed) for r in runs] == [(second, 8), (first, 7)]


async def test_stage_requests_order_token_and_deadline_are_stored(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)
    deadline = datetime(2026, 10, 22, 6, tzinfo=UTC)
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.count_requests(run_id, "collect", 4)
        await repo.count_requests(run_id, "collect", 3)
        await repo.finish_stage(run_id, "collect")
        await repo.set_release(run_id, "71")
        await repo.set_status(run_id, "running")
        await repo.set_deadline(run_id, deadline)
        await repo.set_token(run_id, b"sealed")
        await session.commit()
    async with session_maker() as session:
        run = await AuditRepository(session).run(run_id, user_id=user_id)
        sealed = await AuditRepository(session).sealed_token(run_id)
        stored = await AuditRepository(session).stored_run(run_id)
    assert run is not None
    assert (
        run.stages.requests,
        run.stages.next_stage,
        run.release,
        run.status,
        run.deadline_at,
        sealed,
    ) == (7, "screen", "71", "running", deadline, b"sealed")
    assert stored == run


async def test_a_finished_run_is_stamped_and_a_running_one_is_not(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.set_status(run_id, "finished")
        finished = await repo.run(run_id, user_id=user_id)
        await repo.set_status(run_id, "running")
        running = await repo.run(run_id, user_id=user_id)
        await session.commit()
    assert finished is not None
    assert running is not None
    assert (finished.status, finished.finished_at is None) == ("finished", False)
    assert (running.status, running.finished_at) == ("running", None)


async def test_a_genome_moves_from_pending_through_trying_to_collected(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await new_run(session_maker)
    rows = [gene_row("NF54_SHORT", NF54, 200)]
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF54, "audited"), (RELATIVE, "comparison")])
        await repo.add_genomes(run_id, [(NF54, "audited")])
        await repo.try_genome(run_id, NF54)
        await repo.save_genome(
            run_id,
            CollectedGenome(
                organism=NF54, status="unreached", requests=1, message=UNREACHED
            ),
        )
        assert [g.organism for g in await repo.open_genomes(run_id)] == [RELATIVE, NF54]
        await repo.try_genome(run_id, NF54)
        await repo.save_genome(
            run_id,
            CollectedGenome(organism=NF54, status="collected", genes=rows, requests=2),
        )
        await session.commit()
    async with session_maker() as session:
        repo = AuditRepository(session)
        states = {s.organism: s for s in await repo.genome_states(run_id)}
        collected = await repo.collected_genome(run_id, NF54)
        not_collected = await repo.collected_genome(run_id, RELATIVE)
        still_open = await repo.open_genomes(run_id)
    nf54 = states[NF54]
    assert (
        nf54.status,
        nf54.role,
        nf54.gene_count,
        nf54.requests,
        nf54.attempts,
        nf54.message,
    ) == ("collected", "audited", 1, 3, 2, None)
    assert (states[RELATIVE].status, states[RELATIVE].role) == ("pending", "comparison")
    assert collected == rows
    assert not_collected == []
    assert [g.organism for g in still_open] == [RELATIVE]


async def test_a_genome_that_is_not_open_is_not_tried(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await new_run(session_maker)
    rows = [gene_row("NF54_SHORT", NF54, 200)]
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF54, "audited")])
        await repo.try_genome(run_id, NF54)
        await repo.save_genome(
            run_id,
            CollectedGenome(organism=NF54, status="collected", genes=rows, requests=2),
        )
        with pytest.raises(UnitNotOpenError, match=f"genome {NF54} of run"):
            await repo.try_genome(run_id, NF54)
        with pytest.raises(UnitNotOpenError, match="genome no such organism of run"):
            await repo.try_genome(run_id, "no such organism")
        (state,) = await repo.genome_states(run_id)
        collected = await repo.collected_genome(run_id, NF54)
        await session.commit()
    assert (state.status, state.attempts, state.gene_count, state.requests) == (
        "collected",
        1,
        1,
        2,
    )
    assert collected == rows


async def test_a_genome_that_is_not_tried_is_not_settled(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await new_run(session_maker)
    collected = CollectedGenome(
        organism=NF54, status="collected", genes=[gene_row("A", NF54, 9)], requests=2
    )
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF54, "audited")])
        with pytest.raises(UnitNotOpenError, match=f"genome {NF54} of run"):
            await repo.save_genome(run_id, collected)
        await repo.try_genome(run_id, NF54)
        await repo.save_genome(run_id, collected)
        with pytest.raises(UnitNotOpenError, match=f"genome {NF54} of run"):
            await repo.save_genome(run_id, collected)
        with pytest.raises(UnitNotOpenError, match="genome no such organism of run"):
            await repo.save_genome(
                run_id, CollectedGenome(organism="no such organism", status="failed")
            )
        await session.commit()
    async with session_maker() as session:
        (state,) = await AuditRepository(session).genome_states(run_id)
    assert (state.status, state.attempts, state.requests) == ("collected", 1, 2)


async def test_a_genome_the_worker_stops_on_reopens_until_its_third_stop(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await new_run(session_maker)
    statuses = []
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF54, "audited")])
        for _ in range(3):
            await repo.try_genome(run_id, NF54)
            await repo.sweep_genomes(run_id)
            (swept,) = await repo.genome_states(run_id)
            statuses.append(swept.status)
        await session.commit()
    async with session_maker() as session:
        (state,) = await AuditRepository(session).genome_states(run_id)
    assert statuses == ["pending", "pending", "failed"]
    assert (state.status, state.attempts, state.stopped, state.message) == (
        "failed",
        3,
        3,
        STOPPED_MESSAGE,
    )
    assert STOPPED_MESSAGE == "the worker stopped during this unit 3 times"


async def _units(session_maker: async_sessionmaker[AsyncSession]) -> list[int]:
    async with session_maker() as session:
        return [
            await session.scalar(select(func.count()).select_from(table)) or 0
            for table in (AuditGenome, AuditFinding, AuditEvidence)
        ]


async def test_a_genome_keeps_its_stored_busco_gap_and_one_without_holds_null(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await new_run(session_maker)
    settles = [
        CollectedGenome(
            organism=NF135,
            status="unreached",
            message=UNREACHED,
            priority=NF135_PRIORITY,
        ),
        CollectedGenome(organism=NF135, status="collected"),
        CollectedGenome(organism=NF54, status="collected"),
    ]
    async with session_maker() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF135, "audited"), (NF54, "audited")])
        for genome in settles:
            await repo.try_genome(run_id, genome.organism)
            await repo.save_genome(run_id, genome)
        await session.commit()
    async with session_maker() as session:
        states = await AuditRepository(session).genome_states(run_id)
        stored = await session.execute(
            select(AuditGenome.organism, AuditGenome.priority.is_(None))
            .where(AuditGenome.run_id == run_id)
            .order_by(AuditGenome.id)
        )
        nulls = [tuple(row) for row in stored]
    assert nulls == [(NF135, False), (NF54, True)]
    assert [(s.organism, s.priority) for s in states] == [
        (NF135, NF135_PRIORITY),
        (NF54, None),
    ]
    assert [None if s.priority is None else s.priority.gap for s in states] == [
        5.4,
        None,
    ]


async def test_a_site_purge_deletes_only_that_sites_runs_and_their_units(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)
    async with session_maker() as session:
        findings = AuditFindingRepository(session)
        await AuditRepository(session).add_genomes(run_id, [(NF54, "audited")])
        await findings.add_findings(
            run_id,
            [NewFinding(genome=NF54, target=PAIR, sampled=True, status="screened")],
        )
        (finding,) = await findings.findings(run_id, FindingFilter())
        await findings.save_evidence(finding.id, RELATIVES, requests=1)
        await session.commit()
    assert await _units(session_maker) == [1, 1, 1]
    async with session_maker() as session:
        repo = AuditRepository(session)
        assert await repo.delete_runs(user_id=user_id, site_id="toxodb") == 0
        assert await repo.delete_runs(user_id=user_id, site_id="plasmodb") == 1
        await session.commit()
    async with session_maker() as session:
        assert await AuditRepository(session).run(run_id, user_id=user_id) is None
    assert await _units(session_maker) == [0, 0, 0]


async def test_a_purge_of_every_site_keeps_other_owners_and_applications(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)
    other_user, _ = await new_run(session_maker)
    async with session_maker() as session:
        run = await AuditRepository(session).run(run_id, user_id=user_id)
    assert run is not None
    assert run.conversation_id is not None
    token = application_id_ctx.set("another-application")
    try:
        async with session_maker() as session:
            await AuditRepository(session).create_run(
                user_id=user_id,
                conversation_id=run.conversation_id,
                scope=SCOPE,
                seed=8,
            )
            await session.commit()
    finally:
        application_id_ctx.reset(token)
    async with session_maker() as session:
        repo = AuditRepository(session)
        assert await repo.delete_runs(user_id=user_id, site_id=None) == 1
        await session.commit()
    async with session_maker() as session:
        repo = AuditRepository(session)
        assert await repo.runs(user_id=user_id) == []
        assert [r.seed for r in await repo.runs(user_id=other_user)] == [7]
        token = application_id_ctx.set("another-application")
        try:
            assert [r.seed for r in await repo.runs(user_id=user_id)] == [8]
        finally:
            application_id_ctx.reset(token)


async def test_a_purge_that_names_an_empty_site_is_refused(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, _ = await new_run(session_maker)
    async with session_maker() as session:
        repo = AuditRepository(session)
        with pytest.raises(ValueError, match="names a site"):
            await repo.delete_runs(user_id=user_id, site_id="")
        assert [r.seed for r in await repo.runs(user_id=user_id)] == [7]
