from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest
from veupathdb_mcp.catalog import (
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    DecisionsTransport,
)

from pathfinder.ai.graph import turn_route
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.graph.turn_route import (
    ROUTE_BUILD,
    ROUTE_EXPLORE,
    ROUTE_INTRO,
    ask_the_service,
    build_probability,
    decided_route,
    route_request,
    route_request_for,
    strategy_line,
)
from pathfinder.ai.models.mock.route import scripted_route
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests.unit.ai.lead._budget_stop_turn import TITLE, built_session

REQ = route_request("Count genes with a signal peptide", conversation="", strategy="")


def _mode_question(request: DecisionRequest) -> ChoiceQuestion:
    match request.questions:
        case [ChoiceQuestion() as question]:
            return question
        case _:
            pytest.fail("The request carries one choice question")


def _section(request: DecisionRequest, heading: str, following: str) -> str:
    after = request.input.split(f"\n\n{heading}\n", 1)[1]
    return after.split(f"\n\n{following}\n", 1)[0]


def _choice(build: float) -> DecisionResponse:
    return DecisionResponse.model_validate(
        {
            "answers": [
                {
                    "type": "choice",
                    "name": "mode",
                    "choice": "build" if build >= 0.5 else "explore",
                    "probabilities": [
                        {"value": "build", "probability": build},
                        {"value": "explore", "probability": round(1 - build, 6)},
                    ],
                    "confidence": max(build, 1 - build),
                }
            ],
            "usage": {
                "input_tokens": 412,
                "input_tokens_details": {"cached_tokens": 0},
            },
        }
    )


def answering(build: float) -> DecisionsTransport:
    async def ask(request: DecisionRequest) -> DecisionResponse | None:
        return _choice(build)

    return ask


async def none_answer(request: DecisionRequest) -> DecisionResponse | None:
    return None


async def refusing(request: DecisionRequest) -> DecisionResponse | None:
    return DecisionResponse.model_validate(
        {"answers": [{"type": "refusal", "name": "mode"}]}
    )


async def never_answering(request: DecisionRequest) -> DecisionResponse | None:
    await asyncio.sleep(30)
    return _choice(1.0)


def test_the_request_is_the_measured_one() -> None:
    req = route_request(
        "Count genes with a signal peptide", conversation="", strategy=""
    )
    q = _mode_question(req)
    assert req.model == "gpt-6-luna"
    assert q.name == "mode"
    assert q.instructions == "The mode that should answer the latest message."
    assert [c.value for c in q.choices] == ["build", "explore"]
    assert req.input.startswith(
        "PathFinder is an assistant inside VEuPathDB that has two modes. "
    )
    assert req.input.endswith(
        "## The researcher's latest message\nCount genes with a signal peptide"
    )
    assert "## The conversation so far\n(first message)" in req.input
    assert "## The strategy now\n(empty)" in req.input


def test_the_choices_carry_the_measured_descriptions() -> None:
    build, explore = _mode_question(REQ).choices
    assert build.description.startswith(
        "The message asks PathFinder to build, change, undo, run, show, count or export"
    )
    assert explore.description.endswith("Nothing is built until the researcher agrees.")


def test_the_conversation_is_clipped_to_its_last_2500_characters() -> None:
    conversation = "a" * 500 + "x" * 2500
    req = route_request("m", conversation=conversation, strategy="")
    assert _section(req, "## The conversation so far", "## The strategy now") == (
        "x" * 2500
    )


def test_the_strategy_is_clipped_to_its_last_1500_characters() -> None:
    strategy = "a" * 500 + "s" * 1500
    req = route_request("m", conversation="c", strategy=strategy)
    assert _section(
        req, "## The strategy now", "## The researcher's latest message"
    ) == ("s" * 1500)


def test_an_empty_strategy_reads_empty() -> None:
    assert strategy_line(StrategySession(site_id="plasmodb")) == "(empty)"


def test_a_built_strategy_names_its_final_step_and_count() -> None:
    assert strategy_line(built_session()) == (
        f'Strategy: 1 step; the final step "{TITLE}" returns 70 genes'
    )


async def test_a_sure_build_goes_to_build() -> None:
    assert await decided_route(REQ, answering(build=0.92)) == "build"


async def test_below_the_floor_goes_to_explore() -> None:
    assert await decided_route(REQ, answering(build=0.64)) == "explore"


async def test_no_answer_goes_to_explore() -> None:
    assert await decided_route(REQ, none_answer) == "explore"


async def test_a_refusal_goes_to_explore() -> None:
    assert await decided_route(REQ, refusing) == "explore"


async def test_a_hung_service_goes_to_explore_within_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(turn_route, "ROUTE_TIMEOUT_SECONDS", 0.05)
    started = time.monotonic()
    assert await decided_route(REQ, never_answering) == "explore"
    assert time.monotonic() - started < 1.0


def test_the_build_probability_is_read_from_the_build_choice() -> None:
    assert build_probability(_choice(0.73)) == pytest.approx(0.73)
    assert build_probability(None) is None


async def test_the_service_is_asked_under_the_route_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[DecisionRequest, str]] = []

    async def fake_decide(
        request: DecisionRequest, *, purpose: str
    ) -> DecisionResponse | None:
        asked.append((request, purpose))
        return _choice(0.8)

    monkeypatch.setattr(turn_route, "decide", fake_decide)
    response = await ask_the_service(REQ)
    assert build_probability(response) == pytest.approx(0.8)
    assert asked == [(REQ, "turn route")]


def test_the_mock_routes_by_the_arc_token() -> None:
    explore = asyncio.run(scripted_route("Talk me through it [[arc:explore]]")(REQ))
    build = asyncio.run(scripted_route("Build it [[arc:build-journey]]")(REQ))
    plain = asyncio.run(scripted_route("no token")(REQ))
    assert build_probability(explore) == 0.0
    assert build_probability(build) == 1.0
    assert build_probability(plain) == 1.0


def test_the_route_request_reads_the_thread_and_the_strategy() -> None:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="vectorbase",
        mode="strategy",
        user_prompt="Why is 18 h in the reference?",
        domain=StrategyDomainState(
            exchanges=[
                Exchange(
                    said="Find Aedes genes up at 24 h.",
                    reply="I built one step: 70 genes.",
                ),
                Exchange(
                    kind="card_answer",
                    said="Keep 18 h and 36 h.",
                    reply="Kept both references.",
                    card="Compare against 18 h alone?",
                ),
            ]
        ),
    )
    req = route_request_for(state, built_session())
    assert req.input == (
        ROUTE_INTRO
        + "\n\n## The conversation so far\n"
        + "Researcher: Find Aedes genes up at 24 h.\n"
        + "You replied: I built one step: 70 genes.\n\n"
        + "Researcher answered the card: Keep 18 h and 36 h.\n"
        + "You replied: Kept both references.\n"
        + "You asked on a card: Compare against 18 h alone?"
        + "\n\n## The strategy now\n"
        + f'Strategy: 1 step; the final step "{TITLE}" returns 70 genes'
        + "\n\n## The researcher's latest message\n"
        + "Why is 18 h in the reference?"
    )
    assert [c.description for c in _mode_question(req).choices] == [
        ROUTE_BUILD,
        ROUTE_EXPLORE,
    ]
