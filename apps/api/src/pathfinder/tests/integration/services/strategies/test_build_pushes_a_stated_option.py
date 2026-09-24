"""A criterion that binds an option reaches the parameters WDK is sent.

The spec states the option on a criterion of its own, the structure names one
step, and the step that runs the search has to carry the stated value.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.wdk import (
    NewStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_fold import (
    fold_option_criteria,
)
from pathfinder.domain.strategy.spec_tree import (
    build_step_tree,
)
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import spec_build, step_wdk_push
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.wdk_write_stubs import RecordedPushes, landed_pushes

_SEARCH = "GenesByRNASeqEvidence"
_DEFAULT_DATASET = "all_rnaseq"
_TIMECOURSE = "pfal3D7_Gametocyte_Timecourse_rnaSeq"
_PROMPT = "find genes upregulated in gametocytes"


@dataclass
class _RecordingAPI:
    """The WDK steps this build creates, and the strategy pushes it makes."""

    created: list[dict[str, str]] = field(default_factory=list)
    pushes: RecordedPushes = field(
        default_factory=lambda: landed_pushes(
            77, root_step_id=7001, root_count=412, step_count=1
        )
    )
    next_id: int = 7000

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del record_type, user_id
        self.created.append(dict(spec.search_config.parameters))
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name=_SEARCH,
            search_config=WDKSearchConfig(parameters={}),
        )


@pytest.fixture
def recording_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    """Serve the recording API and let every parameter pass validation."""
    api = _RecordingAPI()

    async def _accept_every_value(
        _ctx: Any, *, parameters: dict[str, Any], callbacks: Any
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=parameters)

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(spec_build, "validate_parameters", _accept_every_value)
    monkeypatch.setattr(spec_build, "reconcile_sync_state_with_wdk", _noop_reconcile)
    monkeypatch.setattr(spec_build, "sync_strategy_for_site", api.pushes.sync)
    return api


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


async def _seed_conversation(db_session: AsyncSession, user: User) -> UUID:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Gametocyte expression",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            strategy_ast=StrategyAst(
                record_type="transcript",
                root=StrategyStepNode(id="step_seed", search_name=_SEARCH),
                wdk_step_ids={},
            ).model_dump(by_alias=True, exclude_none=True, mode="json"),
        ),
    )
    await db_session.commit()
    return conv.id


def _spec() -> OperationalSpec:
    """The framed incident: one search criterion, one option criterion."""
    return OperationalSpec(
        goal="genes upregulated in gametocytes",
        title="Gametocyte expression",
        record_type="transcript",
        criteria=[
            Criterion(
                id="gametocyte_expression",
                text="upregulated in gametocytes",
                search_name=_SEARCH,
                role="seed",
                resolved_params={
                    "organism": MultiPickValue(values=["Pf3D7"]),
                    "dataset": StringValue(value=_DEFAULT_DATASET),
                },
                defaulted_params=["dataset"],
            ),
            Criterion(
                id="gametocyte_timecourse_option",
                text="use the gametocyte timecourse dataset",
                search_name=_SEARCH,
                resolved_params={"dataset": StringValue(value=_TIMECOURSE)},
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="gametocyte_expression")
        ),
    )


def _context(
    conversation_id: UUID, session_maker: async_sessionmaker[AsyncSession]
) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conversation_id), name="Gametocyte expression", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    session.graph = graph
    session.sync_state = WDKSyncState()
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=conversation_id,
        db_session_factory=session_maker,
        user_prompt=_PROMPT,
    )


async def test_the_pushed_step_carries_the_option_and_the_row_records_it(
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    recording_api: _RecordingAPI,
) -> None:
    conversation_id = await _seed_conversation(db_session, seed_user)
    tree = build_step_tree(fold_option_criteria(_spec()).spec)

    outcome = await build_strategy_from_spec(
        deps=_context(conversation_id, session_maker),
        root=tree.root,
    )

    assert outcome.failed_steps == []
    assert recording_api.created == [
        {"organism": '["Pf3D7"]', "dataset": _TIMECOURSE},
    ]
    assert recording_api.pushes.pushed == [(None, _PROMPT)]
    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_strategy(conversation_id)
    persisted = StrategyAst.model_validate(stored.strategy_ast)
    assert persisted.root.parameters["dataset"] == StringValue(value=_TIMECOURSE)
