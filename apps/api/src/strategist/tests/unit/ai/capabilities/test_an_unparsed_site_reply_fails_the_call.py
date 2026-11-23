from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, model_validator
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets import FunctionToolset
from veupathdb.wdk import WDKSearchResponse

from strategist.ai.capabilities.site_reads import SiteReadFailures
from strategist.platform.refusals import agent_capabilities

_ORTHOLOGS = json.loads(
    files("veupathdb.testing.fixtures")
    .joinpath("wdk", "search_genes_by_orthologs.json")
    .read_text()
)["body"]


def _without_the_search_name() -> dict[str, Any]:
    data = {k: v for k, v in _ORTHOLOGS["searchData"].items() if k != "urlSegment"}
    return {**_ORTHOLOGS, "searchData": data}


class _Window(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def _ordered(self) -> _Window:
        if self.end < self.start:
            msg = "end must not come before start"
            raise ValueError(msg)
        return self


def _toolset(retries_seen: list[int]) -> FunctionToolset[None]:
    toolset = FunctionToolset[None]()

    @toolset.tool_plain
    def read_search() -> str:
        return WDKSearchResponse.model_validate(
            _without_the_search_name()
        ).search_data.url_segment

    @toolset.tool_plain
    def read_window(start: int, end: int) -> int:
        return _Window(start=start, end=end).end

    @toolset.tool
    def look(ctx: RunContext[None]) -> str:
        retries_seen.append(ctx.retries.get("read_search", 0))
        return "seen"

    return toolset


def _calls(*parts: ToolCallPart) -> FunctionModel:
    script = [ModelResponse(parts=[part]) for part in parts]

    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        turn = sum(isinstance(m, ModelResponse) for m in messages)
        if turn < len(script):
            return script[turn]
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(_respond)


def _agent(retries_seen: list[int]) -> Agent[None, str]:
    toolsets = [_toolset(retries_seen)]
    return Agent(
        deps_type=type(None),
        toolsets=toolsets,
        capabilities=agent_capabilities(
            [SiteReadFailures[None](reads=frozenset())], toolsets=toolsets
        ),
    )


def _returns(messages: list[ModelMessage], tool: str) -> list[tuple[str, str]]:
    return [
        (part.outcome, str(part.content))
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool
    ]


async def test_a_site_reply_that_does_not_parse_fails_the_call() -> None:
    seen: list[int] = []

    result = await _agent(seen).run(
        "read",
        model=_calls(
            ToolCallPart(tool_name="read_search", args={}),
            ToolCallPart(tool_name="look", args={}),
        ),
    )

    assert (_returns(result.all_messages(), "read_search"), seen) == (
        [
            (
                "failed",
                (
                    "read_search got a reply from the site that did not parse "
                    "(WDKSearchResponse). Nothing was read and the strategy is "
                    "unchanged. Say that the site's reply to this read did not "
                    "parse, and answer from what the turn already holds."
                ),
            )
        ],
        [0],
    )


async def test_a_model_built_from_the_arguments_keeps_its_retry() -> None:
    result = await _agent([]).run(
        "read",
        model=_calls(
            ToolCallPart(tool_name="read_window", args={"start": 5, "end": 2})
        ),
    )

    [(outcome, said)] = _returns(result.all_messages(), "read_window")
    assert (outcome, "end must not come before start" in said) == ("retried", True)
