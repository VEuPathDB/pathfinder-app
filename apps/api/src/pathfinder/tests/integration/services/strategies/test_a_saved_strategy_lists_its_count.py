"""A saved WDK strategy stores its root's count, and the saved listing reads it."""

from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode
from veupathdb.wdk import StrategyAPI

from pathfinder.persistence.repositories import ConversationUpdate
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import wdk_sync
from pathfinder.services.strategies.saved_library import list_saved_strategies
from pathfinder.services.strategies.wdk_sync import (
    ChatOwner,
    WdkChatSpec,
    upsert_chat,
)

_WDK_ID = 881207


def _signal_peptide_and_tm() -> StrategyAst:
    root = StrategyStepNode(
        id="root",
        search_name="__combine__",
        primary_input=StrategyStepNode(id="sp", search_name="GenesWithSignalPeptide"),
        secondary_input=StrategyStepNode(
            id="tm", search_name="GenesByTransmembraneDomains"
        ),
        operator=CombineOp.INTERSECT,
    )
    return StrategyAst(
        record_type="transcript",
        root=root,
        step_counts={"sp": 479, "tm": 840, "root": 116},
    )


async def test_a_saved_strategy_lists_the_count_of_its_root(
    authed_user_id: UUID,
) -> None:
    async with async_session_factory() as session:
        conversation = await upsert_chat(
            conv_repo=ConversationRepository(session),
            owner=ChatOwner(
                user_id=authed_user_id, assistant_id=PATHFINDER_ASSISTANT_ID
            ),
            site_id="plasmodb",
            created_here=True,
            spec=WdkChatSpec(
                wdk_id=_WDK_ID,
                name="UAT saved S7",
                strategy_ast=_signal_peptide_and_tm(),
                record_type="transcript",
                is_saved=True,
                step_count=3,
            ),
        )
        await session.commit()

    async with async_session_factory() as session:
        stored = await ConversationRepository(session).get_strategy(conversation.id)
    listing = await list_saved_strategies(
        async_session_factory, user_id=authed_user_id, site_id="plasmodb"
    )

    assert stored.estimated_size == 116
    assert [(e.name, e.step_count, e.root_count) for e in listing] == [
        ("UAT saved S7", 3, 116)
    ]


async def test_a_detail_fetched_from_the_site_stores_the_roots_count(
    authed_user_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fetched(
        _api: StrategyAPI, _wdk_id: int, *, site_id: str
    ) -> tuple[StrategyAst, bool]:
        del site_id
        return _signal_peptide_and_tm(), True

    monkeypatch.setattr(wdk_sync, "get_strategy_api", lambda _site_id: None)
    monkeypatch.setattr(wdk_sync, "fetch_and_convert", _fetched)
    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        created = await repo.create(
            authed_user_id,
            "plasmodb",
            assistant_id=PATHFINDER_ASSISTANT_ID,
            name="summary only",
        )
        await repo.update_conversation(
            created.id,
            ConversationUpdate(wdk_strategy_id=_WDK_ID, wdk_strategy_id_set=True),
        )
        held = await repo.get_with_strategy(created.id)
        assert held is not None
        _conversation, strategy = await wdk_sync.lazy_fetch_wdk_detail(
            conversation=held[0], strategy=held[1], conv_repo=repo
        )
        await session.commit()

    assert (strategy.step_count, strategy.estimated_size) == (3, 116)
