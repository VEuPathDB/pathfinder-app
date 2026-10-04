"""A generated strategy name is generated anew when an edit takes away what it
names, and a name a person chose is never touched."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb import JSONObject
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.persistence.models import ConversationStrategyView, User
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations import turns
from pathfinder.services.conversations.turns import (
    name_conversation_if_unnamed,
    rename_if_edits_outdated_it,
    turn_start_strategy,
)
from pathfinder.services.strategies.naming import rename_strategy_everywhere

GENERATED = "Naegleria fowleri Peptidase Genes With Signal Peptides"
REGENERATED = "Naegleria fowleri Genes With Signal Peptides"
ORGANISM = "Naegleria fowleri ATCC 30863"
TEXTS = {
    "step_peptidase": "peptidase genes",
    "step_signal": "genes with signal peptides",
}


def _words(texts: dict[str, str]) -> JSONObject:
    return StepWords(criterion_texts=texts).model_dump(by_alias=True, mode="json")


def _leaf(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={"organism": MultiPickValue(values=[ORGANISM])},
    )


def _both() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=_leaf("step_peptidase", "GenesByEcNumber"),
            secondary_input=_leaf("step_signal", "GenesWithSignalPeptide"),
        ),
        metadata=_words(TEXTS),
    )


def _signal_only() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=_leaf("step_signal", "GenesWithSignalPeptide"),
        metadata=_words({"step_signal": TEXTS["step_signal"]}),
    )


@dataclass
class _Titles:
    """The title model: records each seed and answers one title."""

    title: str = REGENERATED
    seeds: list[str] = field(default_factory=list)

    async def __call__(self, seed: str) -> str:
        self.seeds.append(seed)
        return self.title


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncSession]:
    del patch_app_db_engine, db_cleaner

    async def _marks(
        site_id: str, record_type: str | None, search_names: object
    ) -> dict[str, str]:
        del site_id, record_type, search_names
        return {"GenesByEcNumber": "organism", "GenesWithSignalPeptide": "organism"}

    monkeypatch.setattr(turns, "organism_parameters", _marks)
    async with session_maker() as session:
        yield session


async def _thread(session: AsyncSession) -> Conversation:
    owner = User(id=uuid4())
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id="amoebadb",
        name="",
    )
    session.add_all([owner, conversation])
    await session.commit()
    return conversation


async def _write(conversation_id: UUID, ast: StrategyAst) -> None:
    async with async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(strategy_ast=ast),
        )
        await session.commit()


async def _stored(conversation_id: UUID) -> tuple[str, ConversationStrategyView]:
    async with async_session_factory() as session:
        found = await ConversationRepository(session).get_with_strategy(conversation_id)
    assert found is not None
    conversation, strategy = found
    return conversation.name, strategy


async def test_deleting_a_step_the_name_names_generates_the_name_anew(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)
    await _write(conversation.id, _both())
    await name_conversation_if_unnamed(conversation.id, title=GENERATED)
    start = await turn_start_strategy(conversation.id)
    await _write(conversation.id, _signal_only())
    titles = _Titles()

    renamed = await rename_if_edits_outdated_it(
        conversation.id, start=start, title_for=titles
    )

    name, strategy = await _stored(conversation.id)
    assert titles.seeds == [f"{ORGANISM}: genes with signal peptides"]
    assert (renamed, name, strategy.strategy_ast["name"]) == (
        REGENERATED,
        REGENERATED,
        REGENERATED,
    )
    assert strategy.generated_name_steps == ["step_signal"]


async def test_a_name_a_person_chose_is_never_generated_anew(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)
    await _write(conversation.id, _both())
    await name_conversation_if_unnamed(conversation.id, title=GENERATED)
    await rename_strategy_everywhere(
        conversation.id, "My Peptidase Picks", session_factory=async_session_factory
    )
    start = await turn_start_strategy(conversation.id)
    await _write(conversation.id, _signal_only())
    titles = _Titles()

    renamed = await rename_if_edits_outdated_it(
        conversation.id, start=start, title_for=titles
    )

    name, strategy = await _stored(conversation.id)
    assert (renamed, name, titles.seeds) == (None, "My Peptidase Picks", [])
    assert strategy.generated_name_steps is None


async def test_an_edit_that_keeps_the_named_steps_asks_for_no_title(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)
    await _write(conversation.id, _both())
    await name_conversation_if_unnamed(conversation.id, title=GENERATED)
    start = await turn_start_strategy(conversation.id)
    titles = _Titles()

    renamed = await rename_if_edits_outdated_it(
        conversation.id, start=start, title_for=titles
    )

    name, strategy = await _stored(conversation.id)
    assert (renamed, name, titles.seeds) == (None, GENERATED, [])
    assert strategy.generated_name_steps == ["step_peptidase", "step_signal"]


async def test_a_title_written_before_the_build_covers_the_steps_it_built(
    db_session: AsyncSession,
) -> None:
    conversation = await _thread(db_session)
    await name_conversation_if_unnamed(conversation.id, title=GENERATED)
    async with async_session_factory() as session:
        snapshots = await StrategyRevisionRepository(session).has_any(conversation.id)
    _, unbuilt = await _stored(conversation.id)
    await _write(conversation.id, _both())
    titles = _Titles()

    renamed = await rename_if_edits_outdated_it(
        conversation.id, start=None, title_for=titles
    )

    _, built = await _stored(conversation.id)
    assert (snapshots, unbuilt.generated_name_steps) == (False, [])
    assert (renamed, titles.seeds) == (None, [])
    assert built.generated_name_steps == ["step_peptidase", "step_signal"]
