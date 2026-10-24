"""A run halted for its sign-in puts back the units it was reading, and stores why it halted."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.tests._support.audit import NF54
from pathfinder.tests.integration.persistence._audit_runs import (
    PAIR,
    UnitState,
    new_run,
    one_finding,
    unit_states,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


async def _reading(session_maker: async_sessionmaker[AsyncSession]) -> UUID:
    run_id, finding_id = await one_finding(session_maker)
    async with session_maker() as session:
        runs, findings = AuditRepository(session), AuditFindingRepository(session)
        await runs.add_genomes(run_id, [(NF54, "audited")])
        await runs.try_genome(run_id, NF54)
        await runs.sweep_genomes(run_id)
        await runs.try_genome(run_id, NF54)
        await findings.try_finding(finding_id)
        await findings.try_evidence(finding_id, "relatives")
        await session.commit()
    return run_id


async def test_the_units_being_read_reopen_without_a_stop(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _reading(session_maker)
    other = await _reading(session_maker)

    async with session_maker() as session:
        await AuditRepository(session).release_trying(run_id)
        await session.commit()

    async with session_maker() as session:
        released = await unit_states(session, run_id)
        untouched = await unit_states(session, other)
    expected: dict[str, UnitState] = {
        NF54: ("pending", 2, 1, None),
        PAIR.key: ("screened", 1, 0, None),
        f"{PAIR.key}/relatives": ("pending", 1, 0, None),
    }
    assert released == expected
    assert {key: state[0] for key, state in untouched.items()} == {
        NF54: "trying",
        PAIR.key: "trying",
        f"{PAIR.key}/relatives": "trying",
    }


async def test_a_halt_reason_is_stored_on_the_run_and_cleared(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, run_id = await new_run(session_maker)

    async with session_maker() as session:
        await AuditRepository(session).count_requests(run_id, "collect", 4)
        await AuditRepository(session).set_halted(run_id, "sign-in needed")
        await session.commit()
    async with session_maker() as session:
        halted = await AuditRepository(session).run(run_id, user_id=user_id)
        await AuditRepository(session).set_halted(run_id, None)
        await session.commit()
    async with session_maker() as session:
        cleared = await AuditRepository(session).run(run_id, user_id=user_id)

    assert halted is not None
    assert cleared is not None
    assert (halted.stages.halted, halted.stages.requests) == ("sign-in needed", 4)
    assert (cleared.stages.halted, cleared.stages.requests) == (None, 4)


async def test_the_deadline_marks_only_units_never_read(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id, finding_id = await one_finding(session_maker)
    tried_id = await _reading(session_maker)
    async with session_maker() as session:
        runs, findings = AuditRepository(session), AuditFindingRepository(session)
        await runs.add_genomes(run_id, [(NF54, "audited")])
        await runs.unread_genomes(run_id, [NF54], "not read")
        await findings.unread_findings([finding_id], "not read")
        await findings.unread_evidence([finding_id], "relatives", "not read")
        await runs.unread_genomes(tried_id, [NF54], "not read")
        await session.commit()
    async with session_maker() as session:
        unread = await unit_states(session, run_id)
        tried = await unit_states(session, tried_id)
    assert unread == {
        NF54: ("unread", 0, 0, "not read"),
        PAIR.key: ("unread", 0, 0, "not read"),
        f"{PAIR.key}/relatives": ("unread", 0, 0, "not read"),
    }
    assert tried[NF54] == ("trying", 2, 1, None)


async def test_a_unit_tried_before_stays_unreached_when_the_deadline_passes(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _reading(session_maker)
    async with session_maker() as session:
        runs, findings = AuditRepository(session), AuditFindingRepository(session)
        await runs.release_trying(run_id)
        (finding,) = await findings.findings(run_id, FindingFilter())
        await runs.unread_genomes(run_id, [NF54], "not read")
        await findings.unread_findings([finding.id], "not read")
        await findings.unread_evidence([finding.id], "relatives", "not read")
        await session.commit()
    async with session_maker() as session:
        states = await unit_states(session, run_id)
    assert states == {
        NF54: ("unreached", 2, 1, "not read"),
        PAIR.key: ("unreached", 1, 0, "not read"),
        f"{PAIR.key}/relatives": ("unreached", 1, 0, "not read"),
    }
