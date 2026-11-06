from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NoReturn
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import (
    DurableCall,
    DurableTaskResult,
    PendingApproval,
    PendingDurableCall,
)
from assistant_core.platform.types import PaidBy
from assistant_core.quota import QuotaStatus
from langgraph.runtime import Runtime
from pydantic import SecretStr
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionsTransport,
    post_decision,
    use_decisions_transport,
)

from pathfinder.ai.capabilities import decisions_spend
from pathfinder.ai.capabilities.decisions_spend import send_decision
from pathfinder.ai.capabilities.metering import ModelSpend
from pathfinder.ai.graph import route_node
from pathfinder.ai.graph.route_node import parked_route, route_turn_node
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.domain.modes import EXPLORE_PHASE, READINGS_PHASE
from pathfinder.domain.provider_keys import KeyRefusal, ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    OwnKeyRequiredError,
    ProviderKeyError,
    ProviderKeyRefusedError,
    ProviderNotConfiguredError,
)
from pathfinder.platform.model_catalog import install_catalog_prices
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests._support.decisions_wire import DecisionsWire, recorded_decision
from pathfinder.tests._support.explore_turns import chunks_of, update_of
from pathfinder.tests._support.run_context import turn_runtime

RECORDED = recorded_decision("interpro_pick.json")
RECORDED_INPUT_TOKENS = 711
DEPLOYMENT_KEY = "sk-deployment-route-key"
RESEARCHER_KEY = "sk-researcher-route-key"
TASK = uuid4()
UNREADABLE = OperationalError("SELECT used_usd", {}, ConnectionRefusedError())
SPENT = QuotaStatus(
    used_usd=Decimal("2.000000"),
    limit_usd=Decimal("2.0"),
    total_tokens=900,
    percent=1.0,
    resets_at=datetime(2026, 11, 1, tzinfo=UTC),
)


@dataclass
class _Turn:
    payloads: list[object] = field(default_factory=list)
    charged: list[tuple[UUID, list[ModelSpend]]] = field(default_factory=list)

    def chunks(self) -> list[dict[str, Any]]:
        return chunks_of(self.payloads)


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch) -> _Turn:
    recorded = _Turn()

    async def _charge(
        session_factory: object, *, user_id: UUID, spent: Sequence[ModelSpend]
    ) -> None:
        del session_factory
        recorded.charged.append((user_id, list(spent)))

    monkeypatch.setattr(route_node, "charge_spend", _charge)
    monkeypatch.setattr(
        route_node, "get_stream_writer", lambda: recorded.payloads.append
    )
    return recorded


@pytest.fixture
def refusing_decisions(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _refuse(request: DecisionRequest, ask: DecisionsTransport) -> str:
        pytest.fail(f"the router was asked: {request.input[-80:]!r}")

    monkeypatch.setattr(route_node, "decided_route", _refuse)


@dataclass
class _Budget:
    spent: QuotaStatus | None = None
    read_for: list[UUID] = field(default_factory=list)


@pytest.fixture
def live_deployment(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Budget]:
    install_catalog_prices()
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", DEPLOYMENT_KEY)
    budget = _Budget()

    async def _spent(session: AsyncSession, user_id: UUID) -> QuotaStatus | None:
        del session
        budget.read_for.append(user_id)
        return budget.spent

    monkeypatch.setattr(route_node, "spent_deployment_budget", _spent)
    use_decisions_transport(send_decision)
    yield budget
    use_decisions_transport(post_decision)


def _routed_build() -> dict[str, Any]:
    return {
        **RECORDED["response"],
        "answers": [
            {
                "type": "choice",
                "name": "mode",
                "choice": "build",
                "probabilities": [
                    {"value": "build", "probability": 0.9},
                    {"value": "explore", "probability": 0.1},
                ],
                "confidence": 0.9,
            }
        ],
    }


def state(mode: str = "auto", user_prompt: str = "", **fields: Any) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode=mode,
        user_prompt=user_prompt,
        **fields,
    )


def runtime() -> Runtime[Context]:
    return Runtime(context=turn_runtime(db_session_factory=AsyncSession))


def approval(*, phase: str, tool_name: str = "remember") -> PendingApproval:
    return PendingApproval(
        phase=phase, tool_call_id=f"call-{tool_name}", tool_name=tool_name
    )


def answer(card: PendingApproval) -> dict[str, ToolApprovalResponded]:
    return {card.tool_call_id: ToolApprovalResponded(id="approval-1", approved=True)}


def durable(*, phase: str, task: UUID) -> PendingDurableCall:
    return PendingDurableCall(
        phase=phase,
        tool_call_id="call-pca",
        tool_name="run_eda_dimensionality_reduction",
        durable_calls=[
            DurableCall(
                tool_call_id="call-pca",
                tool_name="run_eda_dimensionality_reduction",
                task_id=task,
                durable_tool_name="run_eda_dimensionality_reduction",
            )
        ],
    )


@pytest.mark.usefixtures("turn", "refusing_decisions")
async def test_build_mode_never_asks_the_router() -> None:
    assert (await route_turn_node(state("build", "m"), runtime())).goto == "lead"


@pytest.mark.usefixtures("turn", "refusing_decisions")
async def test_explore_mode_never_asks_the_router() -> None:
    assert (await route_turn_node(state("explore", "m"), runtime())).goto == "explore"


@pytest.mark.usefixtures("turn")
async def test_auto_asks_the_router_of_the_mock_deployment() -> None:
    talk = await route_turn_node(
        state("auto", "Talk it through [[arc:explore]]"), runtime()
    )
    build = await route_turn_node(
        state("auto", "Build it [[arc:build-journey]]"), runtime()
    )
    assert [talk.goto, build.goto] == ["explore", "lead"]


@pytest.mark.usefixtures("turn", "refusing_decisions")
async def test_an_empty_message_in_auto_is_build() -> None:
    assert (await route_turn_node(state("auto", ""), runtime())).goto == "lead"


@pytest.mark.usefixtures("turn", "refusing_decisions")
async def test_a_completion_turn_returns_to_the_agent_that_parked() -> None:
    finished = state(
        "build",
        pending_durable_call=durable(phase=EXPLORE_PHASE, task=TASK),
        durable_result=DurableTaskResult(task_id=TASK, status="success"),
    )
    assert (await route_turn_node(finished, runtime())).goto == "explore"


@pytest.mark.usefixtures("turn", "refusing_decisions")
async def test_a_readings_card_answer_goes_to_the_lead_in_explore_mode() -> None:
    card = approval(phase=READINGS_PHASE, tool_name="consult_user")
    answered = state("explore", pending_approval=card, approval_responses=answer(card))
    assert (await route_turn_node(answered, runtime())).goto == "lead"


@pytest.mark.usefixtures("refusing_decisions")
async def test_a_typed_message_over_the_readings_card_follows_explore_mode(
    turn: _Turn,
) -> None:
    card = approval(phase=READINGS_PHASE, tool_name="consult_user")
    typed = state("explore", "Something else", pending_approval=card)
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command)["pending_approval"]) == (
        "explore",
        None,
    )
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "explore"}}]


@pytest.mark.usefixtures("refusing_decisions")
async def test_a_typed_message_over_the_readings_card_follows_build_mode(
    turn: _Turn,
) -> None:
    card = approval(phase=READINGS_PHASE, tool_name="consult_user")
    typed = state("build", "Something else", pending_approval=card)
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command)["pending_approval"]) == ("lead", None)
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "build"}}]


@pytest.mark.usefixtures("turn")
async def test_a_typed_message_over_the_readings_card_in_auto_asks_the_router() -> None:
    card = approval(phase=READINGS_PHASE, tool_name="consult_user")
    typed = state("auto", "Talk it through [[arc:explore]]", pending_approval=card)
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command)["pending_approval"]) == (
        "explore",
        None,
    )


@pytest.mark.usefixtures("refusing_decisions")
async def test_a_typed_message_over_the_leads_own_card_goes_to_the_lead(
    turn: _Turn,
) -> None:
    card = approval(phase="lead", tool_name="consult_user")
    typed = state("explore", "Something else", pending_approval=card)
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command), turn.chunks()) == (
        "lead",
        {"mode": "build"},
        [],
    )


@pytest.mark.usefixtures("turn", "refusing_decisions")
async def test_a_sub_agent_park_returns_to_the_lead() -> None:
    answered = state("explore", pending_approval=approval(phase="frame"))
    assert (await route_turn_node(answered, runtime())).goto == "lead"


@pytest.mark.usefixtures("refusing_decisions")
async def test_an_answered_explore_card_resumes_explore(turn: _Turn) -> None:
    card = approval(phase=EXPLORE_PHASE)
    answered = state("build", pending_approval=card, approval_responses=answer(card))
    command = await route_turn_node(answered, runtime())
    assert (command.goto, update_of(command), turn.chunks()) == (
        "explore",
        {"mode": "explore"},
        [],
    )


@pytest.mark.usefixtures("refusing_decisions")
async def test_a_typed_message_over_an_explore_card_follows_build_mode(
    turn: _Turn,
) -> None:
    typed = state(
        "build", "Something else", pending_approval=approval(phase=EXPLORE_PHASE)
    )
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command)["pending_approval"]) == ("lead", None)
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "build"}}]


@pytest.mark.usefixtures("refusing_decisions")
async def test_a_typed_message_over_an_explore_card_follows_explore_mode(
    turn: _Turn,
) -> None:
    typed = state(
        "explore", "Something else", pending_approval=approval(phase=EXPLORE_PHASE)
    )
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command)["pending_approval"]) == (
        "explore",
        None,
    )
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "explore"}}]


@pytest.mark.usefixtures("turn")
async def test_a_typed_message_over_an_explore_card_in_auto_asks_the_router() -> None:
    typed = state(
        "auto",
        "Build it [[arc:build-journey]]",
        pending_approval=approval(phase=EXPLORE_PHASE),
    )
    command = await route_turn_node(typed, runtime())
    assert (command.goto, update_of(command)["pending_approval"]) == ("lead", None)


def test_a_task_still_running_parks_no_route() -> None:
    running = state("auto", "m", pending_durable_call=durable(phase="lead", task=TASK))
    assert [parked_route(running)] == [None]


async def test_the_route_is_the_turns_mode_and_its_part(turn: _Turn) -> None:
    command = await route_turn_node(state("explore", "m"), runtime())
    assert update_of(command)["mode"] == "explore"
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "explore"}}]


async def test_a_resume_writes_no_route_part(turn: _Turn) -> None:
    card = approval(phase="lead")
    command = await route_turn_node(
        state("auto", pending_approval=card, approval_responses=answer(card)),
        runtime(),
    )
    assert (update_of(command)["mode"], turn.chunks()) == ("build", [])


async def test_the_router_runs_on_the_deployments_key_and_is_charged(
    turn: _Turn, live_deployment: _Budget
) -> None:
    wire = DecisionsWire(_routed_build())
    asked = state("auto", "Count the genes with a signal peptide", turn_total_tokens=0)
    keyring = ProviderKeyring(active={"openai": SecretStr(RESEARCHER_KEY)})
    with attach_keyring(keyring, build=wire.build):
        command = await route_turn_node(asked, runtime())
    update = update_of(command)
    assert command.goto == "lead"
    assert [auth for _, auth, _ in wire.sent] == [f"Bearer {DEPLOYMENT_KEY}"]
    assert update["turn_total_tokens"] == RECORDED_INPUT_TOKENS
    assert [
        (user, [(s.tokens, s.paid_by) for s in spent]) for user, spent in turn.charged
    ] == [(asked.user_id, [(RECORDED_INPUT_TOKENS, PaidBy.DEPLOYMENT)])]
    assert turn.chunks()[-1]["type"] == "data-turn-usage"
    assert live_deployment.read_for == [asked.user_id]


async def test_a_spent_monthly_allowance_explores_without_asking(
    turn: _Turn, live_deployment: _Budget
) -> None:
    live_deployment.spent = SPENT
    wire = DecisionsWire(_routed_build())
    asked = state("auto", "Count the genes with a signal peptide")
    with attach_keyring(ProviderKeyring(), build=wire.build):
        command = await route_turn_node(asked, runtime())
    assert (command.goto, wire.sent) == ("explore", [])
    assert [s for _, spent in turn.charged for s in spent] == []
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "explore"}}]
    assert live_deployment.read_for == [asked.user_id]


@pytest.mark.usefixtures("live_deployment")
async def test_a_deployment_with_no_openai_key_explores_without_asking(
    turn: _Turn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    wire = DecisionsWire(_routed_build())
    keyring = ProviderKeyring(active={"openai": SecretStr(RESEARCHER_KEY)})
    with attach_keyring(keyring, build=wire.build):
        command = await route_turn_node(state("auto", "Count the genes"), runtime())
    assert (command.goto, wire.sent) == ("explore", [])
    assert [s for _, spent in turn.charged for s in spent] == []


@pytest.mark.parametrize(
    "refusal",
    [
        OwnKeyRequiredError("GPT-6 Luna", "OpenAI"),
        ProviderNotConfiguredError("OpenAI"),
        ProviderKeyRefusedError("OpenAI", KeyRefusal.INVALID),
    ],
)
@pytest.mark.usefixtures("live_deployment")
async def test_a_key_refusal_on_the_router_call_explores(
    turn: _Turn, monkeypatch: pytest.MonkeyPatch, refusal: ProviderKeyError
) -> None:
    def _refuse(model_id: str) -> NoReturn:
        del model_id
        raise refusal

    monkeypatch.setattr(decisions_spend, "deployment_provider", _refuse)
    wire = DecisionsWire(_routed_build())
    with attach_keyring(ProviderKeyring(), build=wire.build):
        command = await route_turn_node(state("auto", "Count the genes"), runtime())
    assert (command.goto, wire.sent) == ("explore", [])
    assert turn.chunks() == [{"type": "data-turn-route", "data": {"route": "explore"}}]


@pytest.mark.usefixtures("turn", "live_deployment")
async def test_a_database_error_reading_the_allowance_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unreadable(session: AsyncSession, user_id: UUID) -> QuotaStatus | None:
        del session, user_id
        raise UNREADABLE

    monkeypatch.setattr(route_node, "spent_deployment_budget", _unreadable)
    with pytest.raises(OperationalError) as raised:
        await route_turn_node(state("auto", "Count the genes"), runtime())
    assert raised.value is UNREADABLE
