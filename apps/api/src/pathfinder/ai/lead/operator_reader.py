from __future__ import annotations

import asyncio
from collections.abc import Sequence
from string import ascii_uppercase

from veupathdb_mcp.catalog import (
    Choice,
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    DecisionsTransport,
    decide,
)

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock.reading import scripted_operators
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.operator_reading import (
    OPERATOR_QUESTION,
    PAIR,
    Branches,
    askable_branches,
    reading_of,
    with_readings,
)
from pathfinder.domain.strategy.operator_reads import OperatorReading
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import is_mock_deployment

_PURPOSE = "operator reading"


def _pair_choices(a: str, b: str) -> list[Choice]:
    return [
        Choice(value="intersect", description=f"records in both {a} and {b}"),
        Choice(value="union", description=f"records in {a}, in {b}, or in both"),
        Choice(
            value="left_minus_right", description=f"records in {a} that are not in {b}"
        ),
        Choice(
            value="right_minus_left", description=f"records in {b} that are not in {a}"
        ),
        Choice(
            value="colocated",
            description=f"records of {a} that lie near records of {b} on the genome",
        ),
        Choice(
            value="not_combined_directly",
            description=f"the messages join {a} and {b} only through another part of the request",
        ),
        Choice(
            value="not_stated",
            description=f"the messages do not say how {a} and {b} combine",
        ),
    ]


def _many_choices(named: str) -> list[Choice]:
    return [
        Choice(value="intersect", description=f"records in every one of {named}"),
        Choice(value="union", description=f"records in any of {named}"),
        Choice(
            value="not_combined_directly",
            description=f"the messages do not join {named} with one operator",
        ),
        Choice(
            value="not_stated",
            description=f"the messages do not say how {named} combine",
        ),
    ]


def operator_request(branches: Branches, messages: Sequence[str]) -> DecisionRequest:
    letters = ascii_uppercase[: len(branches.quotes)]
    names = [f"branch {letter}" for letter in letters]
    said = "\n".join(f"{n}. {m}" for n, m in enumerate(messages, 1))
    listed = "\n\n".join(
        f"## Branch {letter} answers these words of the researcher\n"
        + "\n".join(f'- "{quote}"' for quote in quotes)
        for letter, quotes in zip(letters, branches.quotes, strict=True)
    )
    named = f"{', '.join(names[:-1])} and {names[-1]}"
    choices = _pair_choices(*names) if len(names) == PAIR else _many_choices(named)
    return DecisionRequest(
        input=f"## The researcher's messages, oldest first\n{said}\n\n{listed}",
        questions=[
            ChoiceQuestion(
                name=OPERATOR_QUESTION,
                instructions=(
                    f"How do the researcher's messages combine the records of "
                    f"{named}? Read only the researcher's messages."
                ),
                choices=choices,
            )
        ],
    )


async def _ask_the_service(request: DecisionRequest) -> DecisionResponse | None:
    return await decide(request, purpose=_PURPOSE)


async def _read(
    branches: Branches,
    messages: Sequence[str],
    ask: DecisionsTransport,
    floor: float,
) -> OperatorReading | None:
    response = await ask(operator_request(branches, messages))
    answer = None if response is None else response.choice(OPERATOR_QUESTION)
    if answer is None:
        return None
    return reading_of(
        branches.chain, answer.choice, answer.confidence, floor, branches.ids
    )


async def _newest_first(
    branches: Branches,
    messages: Sequence[str],
    ask: DecisionsTransport,
    floor: float,
) -> OperatorReading | None:
    newest = await _read(branches, messages[-1:], ask, floor)
    if len(messages) == 1 or (
        newest is not None and newest.read in ("agrees", "disagrees")
    ):
        return newest
    return await _read(branches, messages, ask, floor)


async def read_the_operators(
    spec: OperationalSpec,
    deps: LeadDeps,
) -> OperationalSpec:
    state = deps.state
    asked = askable_branches(spec, state.domain.requirements)
    if not asked:
        return with_readings(spec, [])
    ask: DecisionsTransport = (
        scripted_operators(state) if is_mock_deployment() else _ask_the_service
    )
    floor = get_settings().decisions_vocab_min_confidence
    messages = state.researcher_messages()
    read = await asyncio.gather(
        *(_newest_first(b, messages, ask, floor) for b in asked)
    )
    return with_readings(spec, [r for r in read if r is not None])
