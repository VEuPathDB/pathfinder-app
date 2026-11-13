from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import ConversationEvent, Message
from assistant_core.platform.db import async_session_factory
from sqlalchemy import func, select

from strategist.devtools.chat import DEV_USER_ID, parse_run_args, run_once
from strategist.domain.strategy.revision import strategy_revision
from strategist.persistence.repositories.conversation import ConversationRepository
from strategist.persistence.repositories.conversation_update import ConversationUpdate
from strategist.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from strategist.persistence.repositories.user import UserRepository
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.services.conversations.begin import begin_conversation
from strategist.services.strategies.revision_ops import previous_revision
from strategist.tests._support.recorded_searches import (
    serve_recorded_plasmodb,
    suite_search,
)
from strategist.tests.integration.persistence._strategy_shapes import (
    four_step_ast,
    three_step_ast,
)

_SITE = "plasmodb"
_THREE = {"combine": 15, "protease": 13, "gameto": 14}
_FOUR = {"orthologs": 16, **_THREE}


async def _write_strategy(conversation_id: UUID, ids: dict[str, int]) -> None:
    ast = three_step_ast(dict(ids)) if len(ids) == 3 else four_step_ast(dict(ids))
    async with async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=ast, record_type="transcript", step_count=len(ids)
            ),
        )
        await session.commit()


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_a_later_change_is_read_against_the_snapshot_the_turn_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_recorded_plasmodb(
        monkeypatch, [suite_search("search_genes_with_signal_peptide")]
    )
    conversation_id = uuid4()
    async with async_session_factory() as session:
        await UserRepository(session).get_or_create(DEV_USER_ID)
        await begin_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=DEV_USER_ID,
            site_id=_SITE,
            assistant_id=STRATEGIST_ASSISTANT_ID,
        )
        await session.commit()
    await _write_strategy(conversation_id, _THREE)

    code = await run_once(
        parse_run_args(
            [
                "delegation",
                "--site",
                _SITE,
                "--mock",
                "--approve",
                "auto",
                "--quiet",
                "--conversation-id",
                str(conversation_id),
                "--run-dir",
                str(tmp_path / "run"),
            ]
        )
    )
    await _write_strategy(conversation_id, _FOUR)

    assert code == 0
    async with async_session_factory() as session:
        before = await previous_revision(session, conversation_id=conversation_id)
        latest = await StrategyRevisionRepository(session).latest(conversation_id)
        answers = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id, Message.role == "assistant"
            )
        )
        logged = await session.scalar(
            select(func.count())
            .select_from(ConversationEvent)
            .where(ConversationEvent.conversation_id == conversation_id)
        )
    assert before is not None
    assert before.revision == strategy_revision(three_step_ast(dict(_THREE)))
    assert before.message_id is not None
    assert latest is not None
    assert latest.message_id is None
    assert answers == 1
    assert logged is not None
    assert logged > 0
