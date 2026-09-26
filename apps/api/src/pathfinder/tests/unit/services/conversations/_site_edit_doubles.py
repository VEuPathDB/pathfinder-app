"""A thread whose strategy was edited on PlasmoDB, served to both strategy routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode, walk
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails

from pathfinder.domain.strategy.operations import (
    GraphOperation,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.services.conversations import strategy_ops
from pathfinder.services.strategies import (
    commit,
    live_counts,
    site_changes,
    step_wdk_push,
    sync,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
)

SITE = "plasmodb"
STRATEGY = 330679883
EXPORT = "step_exportpred"
TAXON = "step_taxon"
JOIN = "step_join"
WDK = {EXPORT: 440537303, TAXON: 440537304, JOIN: 440537305}
SCORE = "min_exportpred_score"
CEILING = "max_exportpred_score"
ORGANISM = "organism"
RECORD_CLASS = "TranscriptRecordClasses.TranscriptRecordClass"


def stored_ast() -> StrategyAst:
    """The tree PathFinder last wrote: the score at 10, every step on the site."""
    export_params: dict[str, ParamValue] = {
        SCORE: NumberValue(value=10),
        CEILING: NumberValue(value=20),
    }
    taxon_params: dict[str, ParamValue] = {ORGANISM: StringValue(value="Pf3D7")}
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id=JOIN,
            search_name="__combine__",
            operator=CombineOp.INTERSECT,
            display_name="Intersect",
            primary_input=StrategyStepNode(
                id=EXPORT,
                search_name="GenesByExportPred",
                parameters=export_params,
                display_name="exported",
            ),
            secondary_input=StrategyStepNode(
                id=TAXON, search_name="GenesByTaxon", parameters=taxon_params
            ),
        ),
        step_counts={EXPORT: 191, TAXON: 5000, JOIN: 11},
        wdk_step_ids=dict(WDK),
    )


def site_step(
    wdk_id: int,
    search: str,
    params: dict[str, str],
    size: int,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": wdk_id,
        "searchName": search,
        "searchConfig": {"parameters": params},
        "estimatedSize": size,
        "customName": name,
    }


def join_params(operator: str = "INTERSECT") -> dict[str, str]:
    return {
        "bq_left_op_": str(WDK[EXPORT]),
        "bq_right_op_": str(WDK[TAXON]),
        "bq_operator": operator,
    }


def the_site(
    *,
    score: str = "12",
    tree: dict[str, Any] | None = None,
    extra: dict[str, dict[str, Any]] | None = None,
    drop: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """The strategy as WDK answers for it after the researcher's edit."""
    steps = {
        str(WDK[EXPORT]): site_step(
            WDK[EXPORT],
            "GenesByExportPred",
            {SCORE: score, CEILING: "20"},
            85,
            name="exported",
        ),
        str(WDK[TAXON]): site_step(
            WDK[TAXON], "GenesByTaxon", {ORGANISM: "Pf3D7"}, 5000
        ),
        str(WDK[JOIN]): site_step(
            WDK[JOIN], "boolean_question_transcript", join_params(), 2
        ),
    }
    steps = {key: step for key, step in steps.items() if int(key) not in drop}
    steps.update(extra or {})
    return {
        "strategyId": STRATEGY,
        "name": "exported",
        "rootStepId": WDK[JOIN],
        "recordClassName": RECORD_CLASS,
        "stepTree": tree
        or {
            "stepId": WDK[JOIN],
            "primaryInput": {"stepId": WDK[EXPORT]},
            "secondaryInput": {"stepId": WDK[TAXON]},
        },
        "steps": steps,
    }


class SiteAPI(StubAPI):
    """A site holding the strategy as the researcher left it, recording writes."""

    def __init__(self, strategy: dict[str, Any]) -> None:
        super().__init__()
        self.strategy = strategy

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del strategy_id, user_id
        return WDKStrategyDetails.model_validate(self.strategy)


async def decode_numbers(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, dict[str, str]]
) -> None:
    """Decode every wire value the way a number or a single pick decodes."""
    del api
    for node in walk(payload.root):
        held = wire.get(node.id)
        if held is None:
            continue
        node.parameters = {
            name: (
                NumberValue(value=int(value))
                if value.isdigit()
                else StringValue(value=value)
            )
            for name, value in held.items()
        }


def stored_thread() -> tuple[Conversation, ConversationStrategyView]:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        assistant_id="pathfinder",
        site_id=SITE,
        name="exported",
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        wdk_strategy_id=STRATEGY,
        wdk_strategy_created_here=True,
        is_saved=False,
        step_count=3,
        gene_set_auto_imported=False,
        imported_saved_strategy_ids=[],
        estimated_size=None,
        strategy_ast=stored_ast().model_dump(
            by_alias=True, exclude_none=True, mode="json"
        ),
    )
    return conversation, strategy


class Repo(ConversationRepository):
    def __init__(self, site: SiteAPI) -> None:
        self.thread = stored_thread()
        self.site = site

    async def get_with_strategy(
        self, conversation_id: UUID
    ) -> tuple[Conversation, ConversationStrategyView]:
        del conversation_id
        return self.thread

    @property
    def stored(self) -> StrategyAst:
        return StrategyAst.model_validate(self.thread[1].strategy_ast)

    def value(self, step_id: str, name: str) -> ParamValue:
        (node,) = [n for n in walk(self.stored.root) if n.id == step_id]
        return node.parameters[name]


def install_the_site(monkeypatch: pytest.MonkeyPatch, site: dict[str, Any]) -> Repo:
    """Serve the thread, the lock, the persist and the site to both routes."""
    install_stub_api(monkeypatch)
    api = SiteAPI(site)
    for module in (commit, step_wdk_push, sync, live_counts, site_changes):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", decode_numbers)
    repo = Repo(api)

    async def _owned(*_args: Any, **_kwargs: Any) -> Any:
        return repo.thread

    @asynccontextmanager
    async def _lock(*_args: Any, **_kwargs: Any) -> AsyncIterator[None]:
        yield None

    async def _persist(
        *, deps: StrategyMutationContext, graph: StrategyGraph, sync_result: Any
    ) -> None:
        del sync_result
        written = graph.to_strategy_ast(sync_state=deps.strategy_session.sync_state)
        assert written is not None
        conversation, strategy = repo.thread
        repo.thread = (
            conversation,
            strategy.model_copy(
                update={
                    "strategy_ast": written.model_dump(
                        by_alias=True, exclude_none=True, mode="json"
                    )
                }
            ),
        )

    monkeypatch.setattr(strategy_ops, "get_owned_thread", _owned)
    monkeypatch.setattr(strategy_ops, "strategy_write_lock", _lock)
    monkeypatch.setattr(strategy_ops, "ConversationRepository", lambda _s: repo)
    monkeypatch.setattr(strategy_ops, "persist_strategy_ast_to_conversation", _persist)
    monkeypatch.setattr(commit, "persist_strategy_ast_to_conversation", _persist)
    return repo


async def refresh(repo: Repo) -> None:
    conversation = repo.thread[0]
    await strategy_ops.refresh_counts(
        repo, conversation.id, conversation.user_id, site_id=SITE
    )


async def canvas(repo: Repo, op: GraphOperation) -> None:
    conversation = repo.thread[0]
    await strategy_ops.apply_operation(
        repo, conversation.id, conversation.user_id, site_id=SITE, op=op
    )


def wired(repo: Repo) -> dict[str, list[str]]:
    """Each stored step, with the inputs it is wired to."""
    return {
        node.id: [n.id for n in (node.primary_input, node.secondary_input) if n]
        for node in walk(repo.stored.root)
    }
