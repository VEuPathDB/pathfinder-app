from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from assistant_core.persistence.models import Conversation
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)
from veupathdb_mcp.catalog import ValidatedParams, format_param_info_typed

from pathfinder.ai.agents.frame_pick_checks import hold_an_unsettled_pick_to_a_question
from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_dispatch import minted_spec
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.genome_group_arcs import ORTHOLOG_PATTERN
from pathfinder.ai.tools.standalone import _frame_count
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import measurements, spec_build, step_wdk_push
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.options_reads import serve_options_reads
from pathfinder.tests._support.record_classes import list_every_search_under
from pathfinder.tests._support.recorded_counts import wire
from pathfinder.tests._support.recorded_searches import serve_recorded, suite_search
from pathfinder.tests._support.wdk_write_stubs import RecordedPushes, landed_pushes
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_validation,
    serve_params,
    serve_site_listing,
)

pytestmark = pytest.mark.usefixtures("open_job_queue")

_DEFINITION = suite_search("search_genes_by_ortholog_pattern")
_MESSAGE = (
    "Which Plasmodium falciparum 3D7 genes have an ortholog in the listed genomes "
    "but none in Homo sapiens? [[arc:ortholog-in-a-group]]"
)
_LEFT = "%hsap:N%"
_RIGHT = "%hsap:N%pber:N%pfal:N%"
_STRICT = "%hsap:N%pber:Y%pfal:Y%"
_COUNTS = {_LEFT: 1832, _RIGHT: 1335, _STRICT: 484}


@dataclass
class _RecordingAPI:
    created: list[dict[str, str]] = field(default_factory=list)
    combined: list[CombinedStepSpec] = field(default_factory=list)
    pushes: RecordedPushes = field(
        default_factory=lambda: landed_pushes(
            77, root_step_id=7003, root_count=497, step_count=3
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

    async def create_combined_step(
        self,
        spec: CombinedStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del record_type, user_id
        self.combined.append(spec)
        self.next_id += 1
        return WDKIdentifier(id=self.next_id)

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name=ORTHOLOG_PATTERN,
            search_config=WDKSearchConfig(parameters={}),
        )


@pytest.fixture
def recording_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingAPI:
    api = _RecordingAPI()

    async def _accept_every_value(
        _ctx: Any, *, parameters: dict[str, Any], callbacks: Any
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=parameters)

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _recorded(
        _site_id: str,
        _record_type: str,
        _search_name: str,
        params: Mapping[str, ParamValue],
        *,
        timeout_seconds: float | None = None,
    ) -> int | None:
        del timeout_seconds
        return _COUNTS[wire(params, "profile_pattern")]

    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(spec_build, "validate_parameters", _accept_every_value)
    monkeypatch.setattr(spec_build, "reconcile_sync_state_with_wdk", _noop_reconcile)
    monkeypatch.setattr(spec_build, "sync_strategy_for_site", api.pushes.sync)
    monkeypatch.setattr(measurements, "count_search_answer", _recorded)
    list_every_search_under(monkeypatch, "transcript")
    return api


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


async def _conversation(db_session: AsyncSession) -> UUID:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Orthologs in the listed genomes",
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conversation.id,
            strategy_ast=StrategyAst(
                record_type="transcript",
                root=StrategyStepNode(id="step_seed", search_name=ORTHOLOG_PATTERN),
                wdk_step_ids={},
            ).model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
    )
    await db_session.commit()
    return conversation.id


def _context(
    conversation_id: UUID, session_maker: async_sessionmaker[AsyncSession]
) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conversation_id), name="Orthologs", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    session.graph = graph
    session.sync_state = WDKSyncState()
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=conversation_id,
        db_session_factory=session_maker,
        user_prompt=_MESSAGE,
    )


def _serve_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_DEFINITION])
    sheet = format_param_info_typed(_DEFINITION.parameters or [])
    serve_params(monkeypatch, lambda _context: sheet)
    serve_options_reads(monkeypatch, lambda _name: sheet)
    no_validation(monkeypatch)
    serve_site_listing(monkeypatch, [])

    async def _strict_count(*_args: object, **_kwargs: object) -> int:
        return _COUNTS[_STRICT]

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _strict_count)


def _state() -> AgentToolState:
    state = AgentToolState()
    state.request_messages = [_MESSAGE]
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_profile",
            tool="search_for_searches",
            record_type="transcript",
            query=_MESSAGE,
            hits=[
                CatalogHit(
                    name=ORTHOLOG_PATTERN,
                    display_name=_DEFINITION.display_name,
                    record_type="transcript",
                )
            ],
        )
    )
    return state


async def _answer(state: AgentToolState, call: ToolCallPart) -> object:
    if call.tool_name != "set_criterion":
        return "ok"
    args = call.args_as_dict()
    why = args.get("why")
    returned = await set_criterion(
        frame_ctx(state),
        criterion_id=args["criterion_id"],
        text=args["text"],
        search_name=args["search_name"],
        role=args["role"],
        params=args.get("params"),
        why=None if why is None else SearchChoice.model_validate(why),
    )
    return returned.return_value


async def _framed_by_the_mock_model() -> AgentToolState:
    bind_scripted_scope("plasmodb", _MESSAGE)
    state = _state()
    script = role_script("frame")
    messages: list[ModelMessage] = []
    parts: list[ModelRequestPart] = [UserPromptPart(content=_MESSAGE)]
    for _ in range(10):
        pinned = pinned_frame_sheets(frame_ctx(state)) or ""
        messages.append(ModelRequest(parts=parts, instructions=pinned))
        call = script(messages)
        if call.tool_name == "set_structure":
            root = StructureNode.model_validate(call.args_as_dict()["root"])
            await set_structure(frame_ctx(state), root=root)
            return state
        messages.append(ModelResponse(parts=[call]))
        answer = await _answer(state, call)
        parts = [
            ToolReturnPart(
                tool_name=call.tool_name, content=answer, tool_call_id=call.tool_call_id
            )
        ]
    pytest.fail("the mock model never set the structure")


async def test_an_answered_card_pushes_the_minus_with_no_model_in_between(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    recording_api: _RecordingAPI,
) -> None:
    _serve_sheet(monkeypatch)
    conversation_id = await _conversation(db_session)
    state = await _framed_by_the_mock_model()

    held = hold_an_unsettled_pick_to_a_question(
        frame_ctx(state), FrameResult(summary="framed")
    )

    assert isinstance(held, FrameResult)
    assert held.disposition == "needs_user"
    draft = state.operational_spec_draft
    [asked] = held.questions(draft)
    assert [o.label for o in asked.options] == [
        "At least one of 2 genomes (497 genes)",
        "All 2 genomes (484 genes)",
    ]
    assert wire(draft.criteria[0].param_values, "profile_pattern") == _STRICT

    thread = pipeline_state()
    thread.domain.operational_spec = draft
    thread.domain.record_questions([asked])
    apply_option_bindings(
        thread,
        [
            UserQuestionAnswer(
                question_id="q1",
                prompt=asked.question,
                chosen_labels=[asked.options[0].label],
            )
        ],
        sheets={},
    )
    minted = minted_spec(thread.domain.operational_spec)
    outcome = await build_strategy_from_spec(
        deps=_context(conversation_id, session_maker),
        root=minted.tree.root,
    )

    assert outcome.failed_steps == []
    assert [step["profile_pattern"] for step in recording_api.created] == [
        _LEFT,
        _RIGHT,
    ]
    assert recording_api.created[0]["included_species"] == "n/a"
    assert recording_api.created[0]["excluded_species"] == "hsap"
    assert recording_api.created[1]["included_species"] == "n/a"
    assert recording_api.created[1]["excluded_species"] == "hsap, pber, pfal"
    [combined] = recording_api.combined
    assert combined.boolean_operator is CombineOp.MINUS
    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_strategy(conversation_id)
    persisted = StrategyAst.model_validate(stored.strategy_ast)
    assert persisted.root.operator is CombineOp.MINUS
    assert recording_api.pushes.pushed == [(None, _MESSAGE)]
