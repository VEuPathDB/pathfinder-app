from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.explore._explore_instructions import EXPLORE_OFF_TOPIC_REDIRECT
from pathfinder.ai.explore.explore_agent import build_explore_agent
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests.unit.ai.lead._turn_contract_cases import off_topic_deps


async def _first_request(deps: LeadDeps) -> AgentInfo:
    seen: list[AgentInfo] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        seen.append(info)
        return ModelResponse(parts=[TextPart("PathFinder reads pathogen data.")])

    agent = build_explore_agent()
    with agent.override(model=FunctionModel(answer)):
        await agent.run(deps.state.user_prompt, deps=deps)
    return seen[0]


async def test_an_off_topic_message_is_offered_no_tool_and_the_redirect() -> None:
    info = await _first_request(off_topic_deps())

    assert info.function_tools == []
    assert EXPLORE_OFF_TOPIC_REDIRECT in (info.instructions or "")


async def test_a_research_message_keeps_its_tools() -> None:
    info = await _first_request(off_topic_deps(IntentClassification.FOLLOW_UP_QUESTION))

    assert {t.name for t in info.function_tools} >= {"search_for_searches"}
    assert EXPLORE_OFF_TOPIC_REDIRECT not in (info.instructions or "")
