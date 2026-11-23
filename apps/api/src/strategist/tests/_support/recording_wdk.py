from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, override

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import StrategyStep
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    StrategyAPI,
    VEuPathDBClient,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)

from strategist.domain.strategy.session import StrategySession
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests._support.holding_wdk import TOKEN, USER, HoldingWDK


@dataclass
class Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


_STEP_PUSHES = frozenset(
    {
        "create_step",
        "create_combined_step",
        "create_transform_step",
        "update_step_search_config",
        "update_step_properties",
    }
)


class RecordingWDK(StrategyAPI):
    def __init__(self, wdk: HoldingWDK | None = None, *, next_id: int = 9000) -> None:
        self.wdk = wdk or HoldingWDK(next_id=next_id)
        client = VEuPathDBClient(
            base_url="https://plasmodb.invalid/service",
            site_id="plasmodb",
            transport=self.wdk,
        )
        super().__init__(client, user_id=USER)
        veupathdb_auth_token_ctx.set(TOKEN)
        self.calls: list[Call] = []
        self.refuse: Exception | None = None
        self.fail_on_search_names: set[str] = set()

    def _record(self, name: str, /, **kwargs: Any) -> None:
        self.calls.append(Call(name, kwargs))
        if self.refuse is not None and name in _STEP_PUSHES:
            raise self.refuse
        search = kwargs.get("search_name")
        if search is not None and search in self.fail_on_search_names:
            msg = f"synthetic failure for {search}"
            raise WDKError(msg)

    def named(self, name: str) -> list[Call]:
        return [call for call in self.calls if call.name == name]

    def step_ids(self, name: str) -> set[int]:
        return {call.kwargs["step_id"] for call in self.named(name)}

    def holds(
        self,
        steps: Mapping[str, StrategyStep],
        sync_state: WDKSyncState,
        *,
        root_id: str | None = None,
        name: str = "Test",
        description: str = "",
    ) -> None:
        self.wdk.holds(
            steps, sync_state, root_id=root_id, name=name, description=description
        )

    @override
    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        self._record(
            "create_step",
            search_name=spec.search_name,
            parameters=dict(spec.search_config.parameters),
            record_type=record_type,
            custom_name=spec.custom_name,
        )
        return await super().create_step(spec, record_type, user_id)

    @override
    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        self._record(
            "create_combined_step",
            primary_step_id=spec.primary_step_id,
            secondary_step_id=spec.secondary_step_id,
            boolean_operator=spec.boolean_operator.value,
            record_type=record_type,
            custom_name=spec.custom_name,
        )
        return await super().create_combined_step(spec, record_type, user_id)

    @override
    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        self._record(
            "create_transform_step",
            search_name=spec.search_name,
            parameters=dict(spec.search_config.parameters),
            input_step_id=input_step_id,
            record_type=record_type,
            custom_name=spec.custom_name,
        )
        return await super().create_transform_step(
            spec, input_step_id, record_type, user_id=user_id
        )

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
        self._record(
            "update_step_search_config",
            step_id=step_id,
            search_name=search_name,
            record_type=record_type,
            parameters=dict(search_config.parameters),
            search_config=search_config,
        )
        await super().update_step_search_config(
            step_id,
            search_config,
            record_type,
            search_name,
            user_id=user_id,
            held=held,
        )

    @override
    async def update_step_properties(
        self, step_id: int, spec: PatchStepSpec, *, user_id: str | None = None
    ) -> None:
        self._record(
            "update_step_properties",
            step_id=step_id,
            spec=spec,
            custom_name=spec.custom_name,
        )
        await super().update_step_properties(step_id, spec, user_id=user_id)

    @override
    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        self._record("delete_step", step_id=step_id)
        await super().delete_step(step_id, user_id=user_id)

    @override
    async def set_saved(
        self, strategy_id: int, *, is_saved: bool, user_id: str | None = None
    ) -> None:
        self._record("set_saved", strategy_id=strategy_id, is_saved=is_saved)
        await super().set_saved(strategy_id, is_saved=is_saved, user_id=user_id)

    @override
    async def create_strategy(
        self,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        *,
        is_public: bool = False,
        is_saved: bool = False,
        is_internal: bool = False,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        self._record(
            "create_strategy",
            step_tree=step_tree,
            name=name,
            description=description,
            is_saved=is_saved,
            is_internal=is_internal,
        )
        return await super().create_strategy(
            step_tree,
            name,
            description,
            is_public=is_public,
            is_saved=is_saved,
            is_internal=is_internal,
            user_id=user_id,
        )

    @override
    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
        *,
        description: str | None = None,
    ) -> WDKStrategyDetails:
        self._record(
            "update_strategy",
            strategy_id=strategy_id,
            step_tree=step_tree,
            name=name,
            description=description,
        )
        return await super().update_strategy(
            strategy_id, step_tree, name, user_id, description=description
        )


served: dict[str, RecordingWDK] = {}


def held_by_the_site(session: StrategySession) -> None:
    api = served.get("site")
    graph = session.graph
    root_id = None if graph is None else graph.primary_root_id()
    if api is None or graph is None or root_id is None:
        return
    api.holds(
        graph.steps,
        ensure_sync_state(session),
        root_id=root_id,
        name=graph.name,
        description=strategy_description(graph, root_id),
    )
