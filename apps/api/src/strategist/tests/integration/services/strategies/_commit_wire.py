"""The WDK strategy API and the stored thread a commit test runs against."""

from __future__ import annotations

from typing import Any, override
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    WDKSearchConfig,
    WDKStep,
)

from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.persistence.models import ConversationStrategy, User
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.services.strategies import commit_tree, live_counts
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.recording_wdk import (
    RecordingWDK,
    held_by_the_site,
    served,
)
from strategist.tests._support.wdk_write_stubs import keeps_every_value

PROMPT = "find kinases expressed in blood stages"


class CountingAPI(RecordingWDK):
    def __init__(self) -> None:
        super().__init__()

    @override
    async def delete_orphaned_steps(self, step_ids: list[int]) -> list[int]:
        self._record("delete_orphaned_steps", step_ids=list(step_ids))
        return await super().delete_orphaned_steps(step_ids)


def patch_strategy_api(monkeypatch: pytest.MonkeyPatch, api: CountingAPI) -> None:
    """Serve ``api`` to the commit path, and let every step count as complete."""

    monkeypatch.setitem(served, "site", api)
    for module in (commit_tree, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit_tree, "validate_parameters", keeps_every_value)


def orphaned(api: CountingAPI) -> list[list[int]]:
    """The WDK step ids handed to each orphan sweep, in call order."""
    return [
        sorted(c.kwargs["step_ids"])
        for c in api.calls
        if c.name == "delete_orphaned_steps"
    ]


PV = MultiPickValue(values=["Plasmodium vivax PvW1"])


def leaf(id_: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
    )


def combine(
    id_: str,
    p: StrategyStepNode,
    s: StrategyStepNode,
    op: CombineOp = CombineOp.INTERSECT,
) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="__combine__",
        primary_input=p,
        secondary_input=s,
        operator=op,
    )


async def seed_conversation(
    db_session: AsyncSession,
    user: User,
    *,
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
) -> UUID:
    ast = StrategyAst(record_type="transcript", root=root, wdk_step_ids=wdk_step_ids)
    conv = Conversation(
        assistant_id=STRATEGIST_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Test strategy",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=555,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        ),
    )
    await db_session.commit()
    return conv.id


def build_deps(
    *,
    conv_id: UUID,
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
    db_session_factory: Any,
) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conv_id), name="Test strategy", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids),
        wdk_strategy_id=555,
    )
    held_by_the_site(session)
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=conv_id,
        db_session_factory=db_session_factory,
        user_prompt=PROMPT,
    )


class FailingAPI(CountingAPI):
    """Rejects one search name, the way WDK rejects one bad step."""

    fail_search: str = "GenesByTaxon"

    @override
    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
        held: WDKStep | None = None,
    ) -> None:
        if search_name == self.fail_search:
            msg = "WDK rejected this step"
            raise WDKError(msg, 422)
        await super().update_step_search_config(
            step_id,
            search_config,
            record_type,
            search_name,
            user_id=user_id,
            held=held,
        )
