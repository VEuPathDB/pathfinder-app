"""The usage report reads each assistant turn with its thread, site and researcher."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.devtools.usage import build_report
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.usage_report import UsageReportRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


def _turn(conversation_id: UUID, day: int, tokens: int, cost: str) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        metadata_={"usage": {"totalTokens": tokens, "costUsd": cost}},
        created_at=datetime(2026, 10, day, 12, tzinfo=UTC),
    )


async def _seed(session_maker: async_sessionmaker[AsyncSession]) -> tuple[UUID, UUID]:
    async with session_maker() as session:
        user = User(external_id="tester-1")
        session.add(user)
        await session.flush()
        plasmo = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            user_id=user.id,
            site_id="plasmodb",
            name="kinases",
        )
        toxo = Conversation(
            assistant_id="site_help",
            user_id=user.id,
            site_id="toxodb",
            name="help",
        )
        session.add_all([plasmo, toxo])
        await session.flush()
        session.add_all(
            [
                Message(
                    id=uuid4(),
                    conversation_id=plasmo.id,
                    role="user",
                    metadata_={},
                    created_at=datetime(2026, 10, 1, 11, tzinfo=UTC),
                ),
                _turn(plasmo.id, 1, 1000, "0.0100"),
                _turn(plasmo.id, 2, 3000, "0.0300"),
                _turn(toxo.id, 2, 500, "0.0020"),
                Message(
                    id=uuid4(),
                    conversation_id=toxo.id,
                    role="assistant",
                    metadata_={},
                    created_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
                ),
            ],
        )
        await session.commit()
        return plasmo.id, toxo.id


async def test_the_report_groups_turns_by_thread_researcher_and_day(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    plasmo, _ = await _seed(session_maker)
    async with session_maker() as session:
        rows = await UsageReportRepository(session).turns(since=date(2026, 10, 1))

    report = build_report(rows)

    assert [
        (c.label, c.turns, c.total_tokens, c.cost_usd, c.site_id)
        for c in report.conversations
    ] == [
        ("kinases", 2, 4000, Decimal("0.0400"), "plasmodb"),
        ("help", 1, 500, Decimal("0.0020"), "toxodb"),
    ]
    assert [(u.label, u.turns, u.cost_usd) for u in report.users] == [
        ("tester-1", 3, Decimal("0.0420"))
    ]
    assert [(d.label, d.turns, d.cost_usd) for d in report.days] == [
        ("2026-10-01", 1, Decimal("0.0100")),
        ("2026-10-02", 2, Decimal("0.0320")),
    ]
    assert report.turns_per_conversation == Decimal("1.5")
    assert report.cost_per_conversation == Decimal("0.0210")
    assert report.cost_per_turn == Decimal("0.0140")
    assert {row.conversation_id for row in rows} >= {plasmo}


async def test_a_site_filter_keeps_only_that_site_s_turns(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_maker)
    async with session_maker() as session:
        rows = await UsageReportRepository(session).turns(site_id="toxodb")

    assert [(row.site_id, row.total_tokens) for row in rows] == [
        ("toxodb", 0),
        ("toxodb", 500),
    ]
