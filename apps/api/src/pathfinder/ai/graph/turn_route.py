from __future__ import annotations

import asyncio
from typing import Final

from assistant_core.graph.tool_summary import count_noun
from veupathdb_mcp.catalog import (
    Choice,
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    DecisionsTransport,
    decide,
)

from pathfinder.ai.capabilities.decisions_spend import decisions_on_the_deployment
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.tools.standalone.graph_helpers import (
    build_step_response,
    counted_records,
)
from pathfinder.domain.exchanges import exchanges_text
from pathfinder.domain.modes import TurnRoute, route_of_build_probability
from pathfinder.domain.strategy.build_outcome import built_counts
from pathfinder.domain.strategy.session import StrategySession, strategy_root_id

ROUTE_QUESTION: Final = "mode"
ROUTE_TIMEOUT_SECONDS: Final = 5.0
ROUTE_PURPOSE: Final = "turn route"

ROUTE_INTRO: Final = (
    "PathFinder is an assistant inside VEuPathDB that has two modes. Read the researcher's latest message, "
    "with the conversation and the strategy as context, and pick the mode that should answer it."
)
ROUTE_BUILD: Final = (
    "The message asks PathFinder to build, change, undo, run, show, count or export something on a VEuPathDB "
    "search strategy, asks about the current strategy, its steps, counts, searches or results, or answers a "
    "question PathFinder asked. The searches it needs are ones a site states directly."
)
ROUTE_EXPLORE: Final = (
    "The message asks about biology, mechanisms, hypotheses, experiments, literature or resources, states the "
    "researcher's background, or asks for genes by a concept that needs biological reasoning before any site "
    "search can be chosen. Nothing is built until the researcher agrees."
)

_CONVERSATION_CHARS: Final = 2500
_STRATEGY_CHARS: Final = 1500


def route_request(message: str, *, conversation: str, strategy: str) -> DecisionRequest:
    return DecisionRequest(
        input=(
            ROUTE_INTRO
            + "\n\n## The conversation so far\n"
            + (conversation[-_CONVERSATION_CHARS:] or "(first message)")
            + "\n\n## The strategy now\n"
            + (strategy[-_STRATEGY_CHARS:] or "(empty)")
            + "\n\n## The researcher's latest message\n"
            + message
        ),
        questions=[
            ChoiceQuestion(
                name=ROUTE_QUESTION,
                instructions="The mode that should answer the latest message.",
                choices=[
                    Choice(value="build", description=ROUTE_BUILD),
                    Choice(value="explore", description=ROUTE_EXPLORE),
                ],
            )
        ],
    )


def strategy_line(session: StrategySession) -> str:
    graph = session.graph
    if graph is None or not graph.steps:
        return "(empty)"
    held = f"Strategy: {count_noun(len(graph.steps), 'step')}"
    root_id = strategy_root_id(graph, session.sync_state)
    if root_id is None:
        return held
    title = build_step_response(graph, graph.steps[root_id]).display_name
    count = built_counts(graph, session.sync_state).of(root_id)
    if count is None:
        return f'{held}; the final step "{title}"'
    return f'{held}; the final step "{title}" returns {counted_records(count, graph.record_type)}'


def route_request_for(
    state: PipelineState, session: StrategySession
) -> DecisionRequest:
    return route_request(
        state.user_prompt,
        conversation=exchanges_text(state.domain.exchanges),
        strategy=strategy_line(session),
    )


def build_probability(response: DecisionResponse | None) -> float | None:
    answer = None if response is None else response.choice(ROUTE_QUESTION)
    if answer is None:
        return None
    return next(
        (p.probability for p in answer.probabilities if p.value == "build"), None
    )


async def decided_route(request: DecisionRequest, ask: DecisionsTransport) -> TurnRoute:
    try:
        async with asyncio.timeout(ROUTE_TIMEOUT_SECONDS):
            response = await ask(request)
    except TimeoutError:
        return "explore"
    return route_of_build_probability(build_probability(response))


async def ask_the_service(request: DecisionRequest) -> DecisionResponse | None:
    with decisions_on_the_deployment():
        return await decide(request, purpose=ROUTE_PURPOSE)
