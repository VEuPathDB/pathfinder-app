"""The evidence units of an audit finding: one row per kind, tried, stored, failed and swept."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    PseudogeneConfirmation,
)
from pathfinder.persistence.models import AuditEvidence
from pathfinder.persistence.repositories.audit import STOPPED_MESSAGE, UnitNotOpenError
from pathfinder.persistence.repositories.audit_findings import AuditFindingRepository
from pathfinder.tests._support.audit import PIGA_INTACT
from pathfinder.tests.integration.persistence._audit_runs import (
    RELATIVES,
    UNREACHED,
    new_run,
    one_finding,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


async def test_evidence_is_one_row_per_kind_tried_stored_or_failed(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    confirmation = ConfirmationEvidence(
        confirmation=PseudogeneConfirmation(result=PIGA_INTACT)
    )
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.save_evidence(finding_id, confirmation, requests=0)
        await repo.try_evidence(finding_id, "relatives")
        await repo.fail_evidence(
            finding_id, "relatives", status="unreached", message=UNREACHED, requests=1
        )
        await repo.try_evidence(finding_id, "relatives")
        await repo.save_evidence(finding_id, RELATIVES, requests=2)
        await session.commit()
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        evidence = await repo.evidence(run_id, [finding_id])
        none = await repo.evidence(run_id, [])
        elsewhere = await repo.evidence((await new_run(session_maker))[1], [finding_id])
    assert [
        (e.kind, e.status, e.payload, e.requests, e.attempts, e.message)
        for e in evidence
    ] == [
        ("confirmation", "stored", confirmation, 0, 0, None),
        ("relatives", "stored", RELATIVES, 3, 2, None),
    ]
    assert (none, elsewhere) == ([], [])


async def test_evidence_that_is_not_open_is_not_tried_or_settled(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    refused = f"relatives evidence of finding {finding_id}"
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.save_evidence(finding_id, RELATIVES, requests=1)
        with pytest.raises(UnitNotOpenError, match=refused):
            await repo.try_evidence(finding_id, "relatives")
        with pytest.raises(UnitNotOpenError, match=refused):
            await repo.save_evidence(finding_id, RELATIVES, requests=5)
        with pytest.raises(UnitNotOpenError, match=refused):
            await repo.fail_evidence(
                finding_id, "relatives", status="failed", message="no", requests=5
            )
        (row,) = await repo.evidence(run_id, [finding_id])
        await session.commit()
    assert (row.status, row.payload, row.attempts, row.requests, row.message) == (
        "stored",
        RELATIVES,
        0,
        1,
        None,
    )


async def test_failed_evidence_holds_sql_null_and_passes_its_check(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    message = "plasmodb serves no gene row for PF3D7_0000100"
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.try_evidence(finding_id, "relatives")
        await repo.fail_evidence(
            finding_id, "relatives", status="failed", message=message, requests=1
        )
        await session.commit()
    async with session_maker() as session:
        null_payload = await session.scalar(
            select(AuditEvidence.payload.is_(None)).where(
                AuditEvidence.finding_id == finding_id
            )
        )
        (row,) = await AuditFindingRepository(session).evidence(run_id, [finding_id])
    assert null_payload is True
    assert (row.status, row.payload, row.attempts, row.message) == (
        "failed",
        None,
        1,
        message,
    )


async def test_evidence_left_trying_is_swept_like_any_unit(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        await repo.try_evidence(finding_id, "relatives")
        await repo.try_evidence(finding_id, "confirmation")
        await repo.sweep_evidence(run_id, "relatives")
        await session.commit()
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        (row,) = await repo.evidence(run_id, [finding_id], kinds=("relatives",))
        (untouched,) = await repo.evidence(
            run_id, [finding_id], kinds=("confirmation",)
        )
    assert (row.status, row.stopped, row.payload) == ("pending", 1, None)
    assert (untouched.status, untouched.stopped) == ("trying", 0)


async def test_evidence_the_worker_stops_on_three_times_is_failed(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    async with session_maker() as session:
        repo = AuditFindingRepository(session)
        for _ in range(3):
            await repo.try_evidence(finding_id, "relatives")
            await repo.sweep_evidence(run_id, "relatives")
        await session.commit()
    async with session_maker() as session:
        (row,) = await AuditFindingRepository(session).evidence(run_id, [finding_id])
    assert (row.status, row.attempts, row.stopped, row.message) == (
        "failed",
        3,
        3,
        STOPPED_MESSAGE,
    )
