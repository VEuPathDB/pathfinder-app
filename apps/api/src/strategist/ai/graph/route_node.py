from __future__ import annotations

from decimal import Decimal
from typing import Final, Literal

from assistant_core.graph.emit import emit_chunk
from assistant_core.platform.types import PaidBy
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langgraph.types import Command
from veupathdb_mcp.catalog import DecisionsTransport

from strategist.ai.capabilities.decisions_spend import (
    decisions_spend_to,
    the_deployment_decides,
)
from strategist.ai.capabilities.metering import ModelSpend, SpendMeter, charge_spend
from strategist.ai.graph._lead_capture import turn_with_spend
from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import PipelineState
from strategist.ai.graph.stream_events import turn_route_event
from strategist.ai.graph.turn_route import (
    ask_the_service,
    decided_route,
    route_request_for,
)
from strategist.ai.models.mock.route import scripted_route
from strategist.domain.modes import (
    EXPLORE_PHASE,
    READINGS_PHASE,
    TurnRoute,
    route_of_parked_phase,
)
from strategist.platform.model_keys import is_mock_deployment
from strategist.services.turn_payment import spent_deployment_budget

type _Agent = Literal["lead", "explore"]

_AGENT_OF: Final[dict[TurnRoute, _Agent]] = {"build": "lead", "explore": "explore"}
_NEW_TURN: Final = frozenset({EXPLORE_PHASE, READINGS_PHASE})


def parked_route(state: PipelineState) -> TurnRoute | None:
    durable = state.pending_durable_call
    if durable is not None and state.carries_durable_answer:
        return route_of_parked_phase(durable.phase)
    card = state.pending_approval
    if card is None:
        return None
    if card.tool_call_id in state.approval_responses or card.phase not in _NEW_TURN:
        return route_of_parked_phase(card.phase)
    return None


async def _service(
    state: PipelineState, runtime: Runtime[Context]
) -> DecisionsTransport | None:
    if not the_deployment_decides():
        return None
    async with runtime.context.db_session_factory() as session:
        spent = await spent_deployment_budget(session, state.user_id)
    return ask_the_service if spent is None else None


async def _picked_route(
    state: PipelineState, runtime: Runtime[Context], meter: SpendMeter
) -> TurnRoute:
    if state.mode == "explore":
        return "explore"
    if state.mode == "build" or not state.user_prompt:
        return "build"
    ask = (
        scripted_route(state.user_prompt)
        if is_mock_deployment()
        else await _service(state, runtime)
    )
    if ask is None:
        return "explore"

    def spent(tokens: int, cost_usd: Decimal, paid_by: PaidBy) -> None:
        meter.spent.append(
            ModelSpend(tokens=tokens, cost_usd=cost_usd, paid_by=paid_by)
        )

    request = route_request_for(state, runtime.context.strategy_session)
    with decisions_spend_to(spent):
        return await decided_route(request, ask)


async def route_turn_node(
    state: PipelineState, runtime: Runtime[Context]
) -> Command[Literal["lead", "explore"]]:
    parked = parked_route(state)
    if parked is not None:
        return Command(goto=_AGENT_OF[parked], update={"mode": parked})
    writer = get_stream_writer()
    meter = SpendMeter()
    route = await _picked_route(state, runtime, meter)
    emit_chunk(writer, turn_route_event(route))
    await charge_spend(
        runtime.context.db_session_factory, user_id=state.user_id, spent=meter.spent
    )
    totals = turn_with_spend(state, meter, writer)
    return Command(
        goto=_AGENT_OF[route],
        update={
            "mode": route,
            "pending_approval": None,
            "turn_total_tokens": totals.turn_total_tokens,
            "turn_total_cost_usd": totals.turn_total_cost_usd,
        },
    )
