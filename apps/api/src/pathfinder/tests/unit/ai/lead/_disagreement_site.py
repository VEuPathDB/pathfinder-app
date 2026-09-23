"""The strategy edited on VEuPathDB itself, for the turn entry to read back.

The site answers the thread's graph as it stands, with the values the
researcher set there on top. The site, the decoder of its wire values, the
lock and the stored row are stand-ins; the read and the replay are the
production ones.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.wdk import StrategyAPI, WDKStepTree, WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import live_counts, site_changes
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead._disagreement_thread import DisagreementThread

_STRATEGY = 330679883
_FIRST_WDK_ID = 440537300


def _tree(graph: StrategyGraph, step_id: str, ids: dict[str, int]) -> WDKStepTree:
    step = graph.steps[step_id]
    return WDKStepTree(
        step_id=ids[step_id],
        primary_input=(
            None
            if step.primary_input_id is None
            else _tree(graph, step.primary_input_id, ids)
        ),
        secondary_input=(
            None
            if step.secondary_input_id is None
            else _tree(graph, step.secondary_input_id, ids)
        ),
    )


class TheSite:
    """PlasmoDB holding the thread's strategy, with the researcher's own values."""

    def __init__(self, session: StrategySession) -> None:
        self.session = session
        self.moved: dict[str, dict[str, ParamValue]] = {}
        self.reads = 0
        self.stored_writes = 0
        self.refuse: Exception | None = None
        self.pushed: StrategyAst | None = None
        """The tree the site held before the edit the test measures."""

    def remember_the_push(self, thread: DisagreementThread) -> None:
        self.pushed = thread.graph.to_strategy_ast()

    @property
    def graph(self) -> StrategyGraph:
        graph = self.session.get_graph(None)
        assert graph is not None
        return graph

    @property
    def ids(self) -> dict[str, int]:
        return {
            step_id: _FIRST_WDK_ID + n for n, step_id in enumerate(self.graph.steps)
        }

    def tree(self) -> WDKStepTree:
        root = self.graph.primary_root_id()
        assert root is not None
        return _tree(self.graph, root, self.ids)

    def details(self) -> WDKStrategyDetails:
        ids = self.ids
        steps: dict[str, Any] = {}
        for step_id, step in self.graph.steps.items():
            values = {**step.parameters, **self.moved.get(step_id, {})}
            wire = {name: to_wire(value) for name, value in values.items()}
            if step.operator is not None:
                wire = {"bq_operator": step.operator.value}
            steps[str(ids[step_id])] = {
                "id": ids[step_id],
                "searchName": step.search_name or "boolean_question_transcript",
                "searchConfig": {"parameters": wire},
            }
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": _STRATEGY,
                "name": self.graph.name,
                "rootStepId": self.tree().step_id,
                "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
                "stepTree": self.tree().model_dump(by_alias=True),
                "steps": steps,
            }
        )

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del strategy_id, user_id
        self.reads += 1
        if self.refuse is not None:
            raise self.refuse
        return self.details()

    async def decode(
        self, payload: StrategyAst, api: StrategyAPI, wire: dict[str, dict[str, str]]
    ) -> None:
        """Decode a wire value back to the value the researcher set."""
        del api
        by_wire = {
            to_wire(value): value
            for values in self.moved.values()
            for value in values.values()
        }
        for node in walk(payload.root):
            node.parameters = {
                name: by_wire[value]
                for name, value in wire.get(node.id, {}).items()
                if value in by_wire
            }


def install_the_site(thread: DisagreementThread) -> TheSite:
    """Put the thread's strategy on the site and serve the turn entry's read."""
    site = TheSite(thread.session)
    thread.session.sync_state = WDKSyncState(
        wdk_step_ids=site.ids, wdk_strategy_id=_STRATEGY, wdk_step_tree=site.tree()
    )

    @asynccontextmanager
    async def _lock(*_args: Any, **_kwargs: Any) -> AsyncIterator[None]:
        yield None

    async def _stored(*_args: Any, **_kwargs: Any) -> StrategySession:
        return thread.session

    async def _persist(**_kwargs: Any) -> None:
        site.stored_writes += 1

    patch = thread.monkeypatch.setattr
    patch(live_counts, "get_strategy_api", lambda _site_id: site)
    patch(site_changes, "get_strategy_api", lambda _site_id: site)
    patch(site_changes, "canonicalize_synced_parameters", site.decode)
    patch(site_changes, "strategy_write_lock", _lock)
    patch(site_changes, "stored_strategy_session", _stored)
    patch(site_changes, "persist_strategy_ast_to_conversation", _persist)
    return site


def site_sets(site: TheSite, step_id: str, **values: ParamValue) -> None:
    """Set values on one step on the site, as its revise form does."""
    site.moved[step_id] = {**site.moved.get(step_id, {}), **values}
