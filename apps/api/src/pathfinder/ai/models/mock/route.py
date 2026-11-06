from __future__ import annotations

from veupathdb_mcp.catalog import (
    ChoiceAnswer,
    ChoiceProbability,
    DecisionRequest,
    DecisionResponse,
    DecisionsTransport,
)

from pathfinder.ai.graph.turn_route import ROUTE_QUESTION
from pathfinder.ai.models.mock.directive import directive_of


def _answer(build: float) -> DecisionResponse:
    return DecisionResponse(
        answers=[
            ChoiceAnswer(
                type="choice",
                name=ROUTE_QUESTION,
                choice="build" if build else "explore",
                probabilities=[
                    ChoiceProbability(value="build", probability=build),
                    ChoiceProbability(value="explore", probability=1.0 - build),
                ],
                confidence=1.0,
            )
        ]
    )


def scripted_route(prompt: str) -> DecisionsTransport:
    build = 0.0 if directive_of(prompt).arc.startswith("explore") else 1.0

    async def ask(request: DecisionRequest) -> DecisionResponse | None:
        return _answer(build)

    return ask
