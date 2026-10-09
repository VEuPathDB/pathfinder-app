from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.types import PaidBy
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import SecretStr
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model, infer_model
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.graph import _lead_model, lead_node
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import final_reply
from pathfinder.ai.graph.lead_node import _drive_lead_stream, _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.domain.strategy.outside_changes import outside_changes
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.platform.model_keys import (
    GuardedModel,
    attach_keyring,
    turn_deployment_refusals,
    turn_refusals,
)
from pathfinder.tests._support.models import ANTHROPIC_STANDARD
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)
from pathfinder.tests.unit.ai.graph._approval_turn import LEAD_FINAL, Collector
from pathfinder.tests.unit.ai.lead.conftest import final_result_part, tool_script_model
from pathfinder.tests.unit.domain.strategy._builders import combine, leaf

_EXPLANATION = "This request may relate to dangerous pathogen work."
_DECLINED_PROMPT = "What does PF3D7_1133400 encode?"
_NEXT_PROMPT = "Find P. falciparum kinases expressed in gametocytes."
_EARLIER = Exchange(said="Which site holds P. falciparum?", reply="PlasmoDB.")
_WORDED = (
    "Claude Sonnet 5.5 declined this request. Its provider's biological safety "
    'filters blocked it. The provider said: "This request may relate to '
    'dangerous pathogen work." These filters sometimes block legitimate '
    "research questions (false positives). Try rephrasing it, or pick a "
    "different model in Settings."
)


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_quota_offline,
        cancel_event=asyncio.Event(),
    )


def _state(prompt: str, domain: StrategyDomainState | None = None) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=prompt,
        user_message_id=uuid4(),
        domain=domain or StrategyDomainState(),
    )


@pytest.fixture
def anthropic_keys() -> Iterator[ProviderWire]:
    wire = ProviderWire(declines=True, explanation=_EXPLANATION)
    keyring = ProviderKeyring(active={"anthropic": SecretStr("sk-ant-test")})
    with attach_keyring(keyring, build=wire.build):
        yield wire


def _declining_model(wire: ProviderWire) -> Model:
    built = infer_model(
        ANTHROPIC_STANDARD,
        provider_factory=lambda _: wire.build("anthropic", SecretStr("sk-ant-test")),
    )
    with attach_keyring(ProviderKeyring(), build=wire.build) as keys:
        return GuardedModel(built, keys=keys, provider="anthropic", paid_by=PaidBy.USER)


def _drive(
    monkeypatch: pytest.MonkeyPatch, model: Model, state: PipelineState
) -> tuple[_LeadRunCapture, Collector]:
    allow_requests_to_the_wire(monkeypatch)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    capture = _LeadRunCapture()
    writer = Collector()
    emitted: Any = writer
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=LeadDeps(
                state=state, intent=None, runtime=_context(), retrieved_memories=[]
            ),
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    return capture, writer


def _notices(writer: Collector) -> list[dict[str, Any]]:
    return [*writer.chunks_of("error"), *writer.chunks_of("data-turn-withdrawn")]


def test_a_declined_request_withdraws_its_prompt_with_a_plain_notice(
    monkeypatch: pytest.MonkeyPatch, anthropic_keys: ProviderWire
) -> None:
    state = _state(_DECLINED_PROMPT)

    capture, writer = _drive(monkeypatch, _declining_model(anthropic_keys), state)

    assert _notices(writer) == [
        {"type": "error", "errorText": _WORDED},
        {
            "type": "data-turn-withdrawn",
            "data": {"errorText": _WORDED, "messageId": str(state.user_message_id)},
        },
    ]
    assert final_reply(capture, None, change="unchanged") is None


def test_a_declined_request_is_sent_once_and_flags_no_key(
    monkeypatch: pytest.MonkeyPatch, anthropic_keys: ProviderWire
) -> None:
    _drive(monkeypatch, _declining_model(anthropic_keys), _state(_DECLINED_PROMPT))

    assert len(anthropic_keys.requests) == 1
    assert (turn_refusals(), turn_deployment_refusals()) == ({}, {})


def test_an_explanation_that_is_not_one_plain_line_is_left_out(
    monkeypatch: pytest.MonkeyPatch, anthropic_keys: ProviderWire
) -> None:
    anthropic_keys.explanation = "line one\nline two"

    _, writer = _drive(
        monkeypatch, _declining_model(anthropic_keys), _state(_DECLINED_PROMPT)
    )

    assert _notices(writer)[0]["errorText"] == (
        "Claude Sonnet 5.5 declined this request. Its provider's biological "
        "safety filters blocked it. These filters sometimes block legitimate "
        "research questions (false positives). Try rephrasing it, or pick a "
        "different model in Settings."
    )


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[list[ModelMessage]] = []

    def answer(self, messages: list[ModelMessage]) -> Any:
        self.requests.append(list(messages))
        return final_result_part(LEAD_FINAL)


async def _turn(
    state: PipelineState, working: list[PipelineState] | None = None
) -> Command[Any]:
    async def _pre_turn(entered: PipelineState, _context: Context) -> PipelineState:
        copy = entered.model_copy(deep=True)
        if working is not None:
            working.append(copy)
        return copy

    return await _run_lead_turn(
        state,
        Runtime(context=_context()),
        pre_turn=_pre_turn,
        build_agent=build_lead_agent,
    )


def _handed_back_domain(command: Command[Any]) -> StrategyDomainState:
    match command.update:
        case {"domain": StrategyDomainState() as domain}:
            return domain
        case other:
            pytest.fail(f"the turn handed back no domain: {other!r}")


def _rendered(messages: list[ModelMessage]) -> str:
    return " ".join(repr(message) for message in messages)


@pytest.fixture
def offline_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _nothing(*_args: Any) -> list[object]:
        return []

    allow_requests_to_the_wire(monkeypatch)
    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: lambda _chunk: None)
    monkeypatch.setattr(lead_node, "retrieve_memories", _nothing)
    monkeypatch.setattr(lead_node, "_persist_residual_quota", _nothing)


@pytest.mark.usefixtures("offline_turn")
def test_the_turn_after_a_declined_one_never_sends_its_prompt(
    monkeypatch: pytest.MonkeyPatch, anthropic_keys: ProviderWire
) -> None:
    entry = StrategyDomainState(exchanges=[_EARLIER])
    declining = _declining_model(anthropic_keys)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: declining)

    declined = _handed_back_domain(asyncio.run(_turn(_state(_DECLINED_PROMPT, entry))))
    recorder = _Recorder()
    answering = tool_script_model(recorder.answer)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: answering)
    answered = _handed_back_domain(asyncio.run(_turn(_state(_NEXT_PROMPT, declined))))

    assert declined == entry
    sent = _rendered(recorder.requests[0])
    assert _NEXT_PROMPT in sent
    assert _DECLINED_PROMPT not in sent
    assert answered.exchanges[0] == _EARLIER
    assert [exchange.said for exchange in answered.exchanges] == [
        _EARLIER.said,
        _NEXT_PROMPT,
    ]


def test_the_withdrawn_prompt_is_the_one_the_turn_opened_on(
    monkeypatch: pytest.MonkeyPatch, anthropic_keys: ProviderWire
) -> None:
    prompt_id = UUID(int=7)
    state = _state(_DECLINED_PROMPT).model_copy(update={"user_message_id": prompt_id})

    _, writer = _drive(monkeypatch, _declining_model(anthropic_keys), state)

    assert _notices(writer)[1]["data"]["messageId"] == str(prompt_id)


@pytest.mark.usefixtures("offline_turn")
def test_a_withdrawn_turn_hands_finalize_no_check_to_write_notes_from(
    monkeypatch: pytest.MonkeyPatch, anthropic_keys: ProviderWire
) -> None:
    declining = _declining_model(anthropic_keys)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: declining)
    checked_earlier = TurnMarkers(message_id=uuid4(), verification_dispatched=True)
    state = _state(_DECLINED_PROMPT, StrategyDomainState(turn_markers=checked_earlier))

    handed_back = _handed_back_domain(asyncio.run(_turn(state)))
    finalized = state.model_copy(update={"domain": handed_back})

    assert finalized.turn_markers.verification_dispatched is False
    assert finalized.checked_verdict is None


def _tree(*leaves: str) -> StrategyAst:
    root = leaf(leaves[0])
    for index, step_id in enumerate(leaves[1:]):
        root = combine(f"c{index}", root, leaf(step_id))
    return StrategyAst(record_type="transcript", root=root)


@pytest.mark.usefixtures("offline_turn")
def test_a_change_built_before_a_decline_reads_next_turn_as_an_outside_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answered, built = _tree("text"), _tree("text", "go")
    working: list[PipelineState] = []

    def _builds_then_declines(messages: list[ModelMessage]) -> Any:
        del messages
        working[0].domain.answered_graph = built
        msg = "Content filter triggered. Finish reason: 'refusal'"
        raise ContentFilterError(msg)

    declining = tool_script_model(_builds_then_declines)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: declining)
    state = _state(_DECLINED_PROMPT, StrategyDomainState(answered_graph=answered))

    handed_back = _handed_back_domain(asyncio.run(_turn(state, working)))
    changes = outside_changes(handed_back.answered_graph, built)

    assert handed_back.answered_graph == answered
    assert {step.step_id for step in changes.added} == {"c0", "go"}
