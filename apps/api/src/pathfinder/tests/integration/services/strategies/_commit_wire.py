"""The WDK strategy API and the stored thread a commit test runs against."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
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
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import (
    commit,
    step_wdk_push,
    sync,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync_state import WDKSyncState

PROMPT = "find kinases expressed in blood stages"


@dataclass
class Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class CountingAPI:
    calls: list[Call] = field(default_factory=list)
    next_id: int = 9000

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(Call("delete_step", {"step_id": step_id}))

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            Call(
                "create_step",
                {"search_name": spec.search_name, "record_type": record_type},
            ),
        )
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self,
        spec: CombinedStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            Call(
                "create_combined_step",
                {
                    "primary_step_id": spec.primary_step_id,
                    "secondary_step_id": spec.secondary_step_id,
                    "boolean_operator": spec.boolean_operator.value,
                    "record_type": record_type,
                },
            ),
        )
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            Call(
                "create_transform_step",
                {
                    "search_name": spec.search_name,
                    "input_step_id": input_step_id,
                    "record_type": record_type,
                },
            ),
        )
        return WDKIdentifier(id=self._alloc())

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id
        self.calls.append(
            Call(
                "update_step_search_config",
                {
                    "step_id": step_id,
                    "search_name": search_name,
                    "record_type": record_type,
                    "parameters": dict(search_config.parameters),
                },
            ),
        )

    async def update_step_properties(
        self,
        step_id: int,
        spec: PatchStepSpec,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id
        self.calls.append(
            Call("update_step_properties", {"step_id": step_id, "spec": spec})
        )

    async def delete_orphaned_steps(self, step_ids: list[int]) -> list[int]:
        """Delete every id and name the ones the site kept. This fake keeps none."""
        self.calls.append(Call("delete_orphaned_steps", {"step_ids": list(step_ids)}))
        for step_id in step_ids:
            await self.delete_step(step_id)
        return []

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(parameters={}),
        )


def patch_strategy_api(monkeypatch: pytest.MonkeyPatch, api: CountingAPI) -> None:
    """Serve ``api`` to the commit path, and let every step count as complete."""

    async def _noop_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    for module in (commit, step_wdk_push, sync):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate)
    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)


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
        assistant_id=PATHFINDER_ASSISTANT_ID,
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

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        if search_name == self.fail_search:
            msg = "WDK rejected this step"
            raise WDKError(msg, 422)
        await super().update_step_search_config(
            step_id, search_config, record_type, search_name, user_id=user_id
        )
