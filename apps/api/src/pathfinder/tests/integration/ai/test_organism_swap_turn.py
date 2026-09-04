"""The acceptance turn: swap the organism on one criterion, keep the rest.

FRAME re-binds only the criterion the request names, through the real parameter
resolver, and the edit reaches WDK as one step patch. The two criteria the
request never mentions come out byte for byte identical.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.parameters.values import MultiPickValue, SinglePickValue
from pathfinder.domain.parameters.wdk_vocab import VocabOption
from pathfinder.domain.search import SearchContext
from pathfinder.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from pathfinder.domain.strategy.graph_model import flatten_tree
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.domain.strategy.validation import StepValidation
from pathfinder.integrations.veupathdb.wdk_models import (
    WDKSearch,
    WDKSearchConfig,
    WDKSearchResponse,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.services.catalog import param_discovery, searches
from pathfinder.services.catalog.param_dag import ParamFetcher
from pathfinder.services.catalog.param_formatting import ParameterInfo
from pathfinder.services.catalog.param_validation import ValidatedParams
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService
from pathfinder.services.strategies import commit as commit_module
from pathfinder.services.strategies import live_counts, step_wdk_push
from pathfinder.services.strategies import sync as sync_module
from pathfinder.services.strategies.sync_state import WDKSyncState

_PF = "Plasmodium falciparum 3D7"
_PV = "Plasmodium vivax P01"
_DERISI = "DeRisi 3D7 Smoothed"
_ZHU = "Zhu P01 time course"

WDK_IDS = {
    "step_text": 100,
    "step_go": 200,
    "step_c1": 300,
    "step_expr": 400,
    "step_c2": 500,
}

ParamsAt = Callable[[dict[str, str]], list[ParameterInfo]]


@dataclass
class _Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _RecordingAPI:
    calls: list[_Call] = field(default_factory=list)

    def named(self, name: str) -> list[_Call]:
        return [c for c in self.calls if c.name == name]

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(_Call("delete_step", {"step_id": step_id}))

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id, record_type
        self.calls.append(
            _Call(
                "update_step_search_config",
                {
                    "step_id": step_id,
                    "search_name": search_name,
                    "parameters": dict(search_config.parameters),
                },
            )
        )

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByProfile",
            search_config=WDKSearchConfig(parameters={}),
        )

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="Test strategy",
            root_step_id=500,
            step_tree=WDKStepTree(step_id=500),
            steps={
                str(wdk_id): WDKStep(
                    id=wdk_id,
                    search_name="GenesByProfile",
                    search_config=WDKSearchConfig(parameters={}),
                    estimated_size=11,
                )
                for wdk_id in WDK_IDS.values()
            },
        )


def _organism_info() -> ParameterInfo:
    return ParameterInfo(
        name="organism",
        display_name="organism",
        type="multi-pick-vocabulary",
        required=True,
        is_visible=True,
        help="",
        value_format="",
        vocab_leaves=[
            VocabOption(value=_PF, display="P. falciparum 3D7"),
            VocabOption(value=_PV, display="P. vivax P01"),
        ],
    )


def _profileset_info(options: list[VocabOption], default: str) -> ParameterInfo:
    return ParameterInfo(
        name="profileset",
        display_name="profileset",
        type="single-pick-vocabulary",
        required=True,
        is_visible=True,
        help="",
        value_format="",
        default_value=default,
        allowed_values=options,
        vocab_depends_on=["organism"],
    )


def _params_under(context: dict[str, str]) -> list[ParameterInfo]:
    if _PV in context.get("organism", ""):
        return [
            _organism_info(),
            _profileset_info([VocabOption(value=_ZHU, display="Zhu P01")], _ZHU),
        ]
    return [
        _organism_info(),
        _profileset_info([VocabOption(value=_DERISI, display=_DERISI)], _DERISI),
    ]


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    api = _RecordingAPI()
    for module in (commit_module, step_wdk_push, sync_module, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)

    async def _noop_validate_plan(*_a: Any, **_k: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate_plan)

    async def _noop_reconcile(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(commit_module, "reconcile_sync_state_with_wdk", _noop_reconcile)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _chunk: None)

    def _fetch_at(*_args: object) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
            return _params_under(context)

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)

    async def _definition(
        record_type: str, name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del record_type, expand_params
        return WDKSearchResponse(
            searchData=WDKSearch(urlSegment=name),
            validation=StepValidation(level="NONE", is_valid=False),
        )

    client = MagicMock()
    client.get_search_details = _definition
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return (
            WDKSearchResponse(
                searchData=WDKSearch(urlSegment=ctx.search_name),
                validation=StepValidation(level="NONE", is_valid=False),
            ),
            "etag",
        )

    monkeypatch.setattr(param_discovery, "fetch_search_details", _details)
    monkeypatch.setattr(frame_spec, "fetch_search_details", _details)

    async def _validate(*_a: object, **_k: object) -> ValidatedParams:
        return ValidatedParams()

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)
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


def _root() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_c2",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_c1",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=StrategyStepNode(
                id="step_text",
                search_name="GenesByText",
                display_name="protease text",
                parameters={
                    "text_expression": SinglePickValue(value="protease"),
                    "organism": MultiPickValue(values=["Plasmodium"]),
                },
            ),
            secondary_input=StrategyStepNode(
                id="step_go",
                search_name="GenesByGoTerm",
                display_name="proteolysis GO",
                parameters={
                    "go_term": SinglePickValue(value="GO:0006508"),
                    "organism": MultiPickValue(values=["Plasmodium"]),
                },
            ),
        ),
        secondary_input=StrategyStepNode(
            id="step_expr",
            search_name="GenesByProfile",
            display_name="expression profile",
            parameters={
                "organism": MultiPickValue(values=[_PF]),
                "profileset": SinglePickValue(value=_DERISI),
            },
        ),
    )


def _before() -> OperationalSpec:
    return spec_from_ast(
        StrategyAst(record_type="transcript", root=_root()),
        goal="proteases with an expression profile",
    )


async def _seed(db_session: AsyncSession, user: User) -> UUID:
    ast = StrategyAst(
        record_type="transcript", root=_root(), wdk_step_ids=dict(WDK_IDS)
    )
    conv = Conversation(
        id=uuid4(), user_id=user.id, site_id="plasmodb", name="Test strategy"
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=777,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
    )
    await db_session.commit()
    return conv.id


def _deps(conv_id: UUID, session_maker: Any) -> LeadDeps:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conv_id), name="Test strategy", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_root())
    graph.recompute_roots()
    graph.last_step_id = "step_c2"
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(WDK_IDS), wdk_strategy_id=777, step_counts={}
    )
    before = _before()
    state = PipelineState(
        conversation_id=conv_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="use P. vivax P01 for the expression profile, keep the rest",
        domain=StrategyDomainState(
            operational_spec=before.model_copy(deep=True),
            spec_before_turn=before.model_copy(deep=True),
        ),
    )
    runtime = Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=session,
        db_session_factory=session_maker,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
    )
    return LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])


def _frame_that_swaps_the_organism(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """FRAME re-binds only the expression criterion, through the real resolver."""
    rounds: list[str] = []

    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        ctx = MagicMock()
        ctx.tool_call_id = "call_1"
        ctx.deps = agent_deps
        first = (
            await set_criterion(
                ctx,
                criterion_id="step_expr",
                text="expression profile",
                search_name="GenesByProfile",
                params={"organism": [_PV], "profileset": _DERISI},
            )
        ).return_value
        rounds.extend(entry.name for entry in first.redecide)
        await set_criterion(
            ctx,
            criterion_id="step_expr",
            text="expression profile",
            search_name="GenesByProfile",
            params={"organism": [_PV], "profileset": _ZHU},
        )
        return FrameResult(
            disposition="spec_ready",
            summary="expression profile moved to P. vivax P01",
            changes=[
                CriterionChange(criterion_id="step_text", disposition="kept"),
                CriterionChange(criterion_id="step_go", disposition="kept"),
                CriterionChange(
                    criterion_id="step_expr",
                    disposition="changed",
                    changed_params={"organism": f'["{_PV}"]', "profileset": _ZHU},
                ),
            ],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    return rounds


async def test_the_swap_re_resolves_the_dependent_and_keeps_the_rest(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    wdk: _RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    before = _before()
    redecided = _frame_that_swaps_the_organism(monkeypatch)

    result = await run_edit(
        deps=deps, parent_tool_call_id="t1", reason="swap the profile organism"
    )

    assert isinstance(result, EditDelta)
    # The dependent was handed back rather than copied forward.
    assert redecided == ["profileset"]
    after = deps.state.domain.operational_spec
    assert after is not None
    swapped = next(c for c in after.criteria if c.id == "step_expr")
    assert swapped.resolved_params["organism"] == MultiPickValue(values=[_PV])
    assert swapped.resolved_params["profileset"] == SinglePickValue(value=_ZHU)
    # Every criterion the request never named is byte for byte what it was.
    for criterion_id in ("step_text", "step_go"):
        was = next(c for c in before.criteria if c.id == criterion_id)
        now = next(c for c in after.criteria if c.id == criterion_id)
        assert now.resolved_params == was.resolved_params
        assert now.search_name == was.search_name


async def test_the_swap_patches_one_step_and_keeps_every_wdk_id(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    wdk: _RecordingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _seed(db_session, seed_user)
    deps = _deps(conv_id, session_maker)
    _frame_that_swaps_the_organism(monkeypatch)

    result = await run_edit(
        deps=deps, parent_tool_call_id="t1", reason="swap the profile organism"
    )

    assert isinstance(result, EditDelta)
    assert [c.kwargs["step_id"] for c in wdk.named("update_step_search_config")] == [
        400
    ]
    assert wdk.named("delete_step") == []
    sync_state = deps.runtime.strategy_session.sync_state
    assert sync_state is not None
    assert sync_state.wdk_step_ids == WDK_IDS
    assert result.diff.render() == "kept 2, changed 1, added 0, dropped 0"
    assert sorted(result.preserved_step_ids) == ["step_go", "step_text"]
