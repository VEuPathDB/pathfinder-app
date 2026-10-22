"""The audit finding rows: written once, filtered, tried, settled, swept and tallied."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.findings import FindingTally
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.persistence.models import AuditFindingRecord
from pathfinder.persistence.repositories.audit import STOPPED_MESSAGE, UnitNotOpenError
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.tests._support.audit import NF54, NF54_PIGA, P3D7, PIGA
from pathfinder.tests.integration.persistence._audit_runs import (
    PAIR,
    SHORT,
    UNREACHED,
    new_run,
    one_finding,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

TRUNCATED = SettledFinding(
    status="confirmed", error_type="truncated_model", certainty="high", requests=4
)


async def _run(session_maker: async_sessionmaker[AsyncSession]) -> UUID:
    _, run_id = await new_run(session_maker)
    return run_id


async def _settle(
    repo: AuditFindingRepository, finding_id: int, settled: SettledFinding
) -> None:
    await repo.try_finding(finding_id)
    await repo.settle_finding(finding_id, settled)


async def test_findings_are_written_once_filtered_tried_and_settled(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    new = [
        NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
        NewFinding(genome=NF54, target=PAIR, sampled=False, status="unsampled"),
    ]
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(run_id, new)
        await repo.add_findings(run_id, new)
        assert await repo.count_findings(run_id, FindingFilter()) == 2
        (pending,) = await repo.findings(
            run_id, FindingFilter(sampled=True, statuses=("screened", "unreached"))
        )
        assert pending.target == SHORT
        unreached = SettledFinding(status="unreached", requests=2, message=UNREACHED)
        await _settle(repo, pending.id, unreached)
        await _settle(repo, pending.id, TRUNCATED)
        await session.commit()
    async with session_maker() as session:
        settled = await AuditFindingRepository(session).finding(run_id, pending.id)
        elsewhere = await AuditFindingRepository(session).finding(
            await _run(session_maker), pending.id
        )
    assert settled is not None
    assert (
        settled.status,
        settled.error_type,
        settled.certainty,
        settled.requests,
        settled.attempts,
        settled.message,
    ) == ("confirmed", "truncated_model", "high", 6, 2, None)
    assert elsewhere is None


async def test_filters_select_by_check_genome_error_naming_and_page(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    other = SingleGeneTarget(check="gene_length", genes=("PF3D7_SHORT",))
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
                NewFinding(genome=NF54, target=PAIR, sampled=True, status="screened"),
                NewFinding(genome=P3D7, target=other, sampled=True, status="screened"),
            ],
        )
        short, pair, _ = await repo.findings(run_id, FindingFilter())
        await _settle(repo, short.id, TRUNCATED)
        await _settle(repo, pair.id, SettledFinding(status="confirmed"))
        await session.commit()

    async def keys(
        where: FindingFilter, *, offset: int = 0, limit: int | None = None
    ) -> list[str]:
        async with session_maker() as session:
            found = await AuditFindingRepository(session).findings(
                run_id, where, offset=offset, limit=limit
            )
        return [f.target.key for f in found]

    async with session_maker() as session:
        counted = await AuditFindingRepository(session).count_findings(
            run_id, FindingFilter(checks=("gene_length",))
        )
    assert counted == 2
    assert await keys(FindingFilter(checks=("gene_length",))) == [
        SHORT.key,
        other.key,
    ]
    assert await keys(FindingFilter(genome=P3D7)) == [other.key]
    assert await keys(FindingFilter(error_types=("truncated_model",))) == [SHORT.key]
    assert await keys(FindingFilter(named=True)) == [SHORT.key]
    assert await keys(FindingFilter(named=False)) == [PAIR.key, other.key]
    assert await keys(FindingFilter(statuses=("confirmed",)), offset=1, limit=1) == [
        PAIR.key
    ]
    assert await keys(FindingFilter(sampled=False)) == []


async def test_a_finding_left_trying_reopens_until_its_third_stop(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    swept: list[AuditFindingRecord | None] = []
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        for _ in range(3):
            await repo.try_finding(finding_id)
            await repo.sweep_findings(run_id)
            swept.append(await repo.finding(run_id, finding_id))
        await session.commit()
    assert [
        None if s is None else (s.status, s.attempts, s.stopped, s.message)
        for s in swept
    ] == [
        ("screened", 1, 1, None),
        ("screened", 2, 2, None),
        ("failed", 3, 3, STOPPED_MESSAGE),
    ]


async def test_a_finding_that_is_not_open_is_not_tried(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
                NewFinding(genome=NF54, target=PAIR, sampled=False, status="unsampled"),
            ],
        )
        confirmed, unsampled = await repo.findings(run_id, FindingFilter())
        await _settle(repo, confirmed.id, TRUNCATED)
        for finding_id in (confirmed.id, unsampled.id):
            with pytest.raises(UnitNotOpenError, match=f"finding {finding_id} is not"):
                await repo.try_finding(finding_id)
        after = await repo.findings(run_id, FindingFilter())
        await session.commit()
    assert [(f.status, f.error_type, f.attempts, f.requests) for f in after] == [
        ("confirmed", "truncated_model", 1, 4),
        ("unsampled", None, 0, 0),
    ]


async def test_a_finding_settles_once_and_counts_its_requests_once(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        with pytest.raises(UnitNotOpenError, match=f"finding {finding_id} is not"):
            await repo.settle_finding(finding_id, TRUNCATED)
        await _settle(repo, finding_id, TRUNCATED)
        with pytest.raises(UnitNotOpenError, match=f"finding {finding_id} is not"):
            await repo.settle_finding(finding_id, TRUNCATED)
        settled = await repo.finding(run_id, finding_id)
        await session.commit()
    assert settled is not None
    assert (settled.status, settled.attempts, settled.requests) == ("confirmed", 1, 4)


async def test_a_finding_failed_by_the_stop_cap_refuses_a_late_settle(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        for _ in range(3):
            await repo.try_finding(finding_id)
            await repo.sweep_findings(run_id)
        with pytest.raises(UnitNotOpenError, match=f"finding {finding_id} is not"):
            await repo.settle_finding(finding_id, TRUNCATED)
        capped = await repo.finding(run_id, finding_id)
        await session.commit()
    assert capped is not None
    assert (
        capped.status,
        capped.attempts,
        capped.stopped,
        capped.message,
        capped.requests,
    ) == ("failed", 3, 3, STOPPED_MESSAGE, 0)


def test_a_settlement_names_an_error_only_when_confirmed_and_certain() -> None:
    with pytest.raises(ValidationError, match="only a confirmed finding"):
        SettledFinding(status="failed", error_type="truncated_model", certainty="high")
    with pytest.raises(ValidationError, match="named together"):
        SettledFinding(status="confirmed", error_type="truncated_model")
    with pytest.raises(ValidationError, match="named together"):
        SettledFinding(status="confirmed", certainty="high")


def test_a_new_finding_is_unsampled_exactly_when_it_is_not_sampled() -> None:
    with pytest.raises(ValidationError, match="unsampled exactly when it is not"):
        NewFinding(genome=NF54, target=PAIR, sampled=True, status="unsampled")
    with pytest.raises(ValidationError, match="unsampled exactly when it is not"):
        NewFinding(genome=NF54, target=PAIR, sampled=False, status="screened")
    with pytest.raises(ValidationError, match="unsampled exactly when it is not"):
        NewFinding(
            genome="", target=PAIR, sampled=False, status="unreached", message="x"
        )


def test_a_new_finding_names_why_exactly_when_it_is_unreached() -> None:
    with pytest.raises(ValidationError, match="names why exactly when"):
        NewFinding(genome="", target=PAIR, sampled=True, status="unreached")
    with pytest.raises(ValidationError, match="names why exactly when"):
        NewFinding(
            genome=NF54, target=PAIR, sampled=True, status="screened", message="x"
        )


async def test_an_unreached_new_finding_is_stored_open_with_its_message(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    async with session_maker() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [
                NewFinding(
                    genome="",
                    target=PAIR,
                    sampled=True,
                    status="unreached",
                    message="plasmodb did not answer",
                )
            ],
        )
        await session.commit()
    async with session_maker() as session:
        (found,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter()
        )
    assert (found.genome, found.status, found.sampled, found.attempts) == (
        "",
        "unreached",
        True,
        0,
    )
    assert found.message == "plasmodb did not answer"


async def test_finding_keys_name_each_findings_genome_and_target(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    async with session_maker() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
                NewFinding(genome="", target=PAIR, sampled=True, status="screened"),
            ],
        )
        await session.commit()
    async with session_maker() as session:
        keys = await AuditFindingRepository(session).finding_keys(run_id)
    assert keys == [
        (NF54, "gene_length:NF54_SHORT"),
        ("", f"pseudogene_call:{NF54_PIGA}+{PIGA}"),
    ]


async def test_a_settle_writes_a_genome_only_when_it_names_one(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
                NewFinding(genome="", target=PAIR, sampled=True, status="screened"),
            ],
        )
        stored, placed = await repo.findings(run_id, FindingFilter())
        await _settle(repo, stored.id, TRUNCATED)
        await _settle(
            repo,
            placed.id,
            SettledFinding(
                status="failed", genome=P3D7, screened_genome=P3D7, message="refused"
            ),
        )
        await session.commit()
    async with session_maker() as session:
        keys = await AuditFindingRepository(session).finding_keys(run_id)
    assert keys == [
        (NF54, "gene_length:NF54_SHORT"),
        (P3D7, f"pseudogene_call:{NF54_PIGA}+{PIGA}"),
    ]


async def test_the_tally_groups_by_genome_check_status_and_error(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _run(session_maker)
    unsampled = SingleGeneTarget(check="gene_length", genes=("NF54_X",))
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
                NewFinding(
                    genome=NF54, target=unsampled, sampled=False, status="unsampled"
                ),
                NewFinding(genome=NF54, target=PAIR, sampled=True, status="screened"),
            ],
        )
        _, _, pair = await repo.findings(run_id, FindingFilter())
        await _settle(
            repo,
            pair.id,
            SettledFinding(
                status="confirmed",
                error_type="intact_gene_called_pseudogene",
                certainty="high",
            ),
        )
        await session.commit()
    async with session_maker() as session:
        tally = await AuditTallyRepository(session).tally(run_id)
    assert tally == [
        FindingTally(
            genome=NF54,
            model_genome=NF54,
            check="gene_length",
            status="screened",
            error_type=None,
            count=1,
            judged=True,
        ),
        FindingTally(
            genome=NF54,
            model_genome=NF54,
            check="gene_length",
            status="unsampled",
            error_type=None,
            count=1,
            judged=True,
        ),
        FindingTally(
            genome=NF54,
            model_genome=NF54,
            check="pseudogene_call",
            status="confirmed",
            error_type="intact_gene_called_pseudogene",
            count=1,
            judged=True,
        ),
    ]
