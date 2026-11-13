from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

from strategist.ai.agents.research_reads import RESEARCH_UNAVAILABLE
from strategist.ai.explore._explore_instructions import EXPLORE_OFF_TOPIC_REDIRECT
from strategist.ai.explore.explore_agent import build_explore_agent
from strategist.ai.lead.contract_messages import off_topic_essay_message
from strategist.ai.lead.intent import IntentClassification
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import OFF_TOPIC_REPLY_MAX_CHARS
from strategist.tests._support.offered_tools import (
    offered_tool_names,
    served_tool_names,
)
from strategist.tests.unit.ai.lead._turn_contract_cases import (
    AN_ESSAY,
    REDIRECT,
    off_topic_deps,
)

_NAMED = re.compile(r"``([a-z_][a-z0-9_]*)``")


def _named_tools(instructions: str | None) -> set[str]:
    return set(_NAMED.findall(instructions or "")) & offered_tool_names()


def _paper(query: str) -> str:
    return f"one paper on {query}"


def _with_research(deps: LeadDeps) -> LeadDeps:
    served: FunctionToolset[object] = FunctionToolset()
    for name in sorted(served_tool_names()):
        served.add_function(_paper, name=name)
    deps.runtime = replace(deps.runtime, tool_sources={"research": served})
    return deps


@dataclass
class _Run:
    seen: list[AgentInfo] = field(default_factory=list)
    sent: list[list[ModelMessage]] = field(default_factory=list)
    output: str = ""

    def corrections(self) -> list[str]:
        return [
            str(part.content)
            for message in self.sent[-1][1:]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart)
        ]


async def _run(deps: LeadDeps, *answers: str) -> _Run:
    run = _Run()

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        run.seen.append(info)
        run.sent.append(list(messages))
        return ModelResponse(parts=[TextPart(answers[len(run.seen) - 1])])

    agent = build_explore_agent()
    with agent.override(model=FunctionModel(answer)):
        result = await agent.run(deps.state.user_prompt, deps=deps)
    assert isinstance(result.output, str)
    run.output = result.output
    return run


@pytest.mark.parametrize("served", [True, False])
async def test_an_off_topic_turn_offers_every_tool_its_instructions_name(
    served: bool,
) -> None:
    deps = _with_research(off_topic_deps()) if served else off_topic_deps()

    [info] = (await _run(deps, REDIRECT)).seen

    named = _named_tools(info.instructions)
    offered = {t.name for t in info.function_tools}
    assert "search_for_searches" in named
    assert sorted(named - offered) == []
    assert EXPLORE_OFF_TOPIC_REDIRECT in (info.instructions or "")


async def test_a_turn_names_the_research_reads_when_the_source_resolved() -> None:
    deps = _with_research(off_topic_deps(IntentClassification.FOLLOW_UP_QUESTION))

    [info] = (await _run(deps, REDIRECT)).seen

    assert served_tool_names() <= _named_tools(info.instructions)
    assert RESEARCH_UNAVAILABLE not in (info.instructions or "")
    assert EXPLORE_OFF_TOPIC_REDIRECT not in (info.instructions or "")


async def test_a_turn_without_the_research_source_says_it_is_unavailable() -> None:
    [info] = (
        await _run(off_topic_deps(IntentClassification.FOLLOW_UP_QUESTION), REDIRECT)
    ).seen

    assert RESEARCH_UNAVAILABLE in (info.instructions or "")
    assert served_tool_names() & _named_tools(info.instructions) == set()


async def test_an_off_topic_reply_longer_than_a_redirect_is_corrected_once() -> None:
    run = await _run(off_topic_deps(), AN_ESSAY, REDIRECT)

    assert len(AN_ESSAY) > OFF_TOPIC_REPLY_MAX_CHARS
    assert (len(run.seen), run.output) == (2, REDIRECT)
    [retry] = run.corrections()
    assert off_topic_essay_message(OFF_TOPIC_REPLY_MAX_CHARS) in retry


async def test_a_long_reply_to_a_research_question_stands() -> None:
    run = await _run(off_topic_deps(IntentClassification.FOLLOW_UP_QUESTION), AN_ESSAY)

    assert (len(run.seen), run.output) == (1, AN_ESSAY)
