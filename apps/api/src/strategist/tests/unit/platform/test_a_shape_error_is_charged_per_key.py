"""A tool argument the schema refuses is charged to the refusal ledger per key,
names every invalid field, and never spends the tool's own retries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal

import pytest
from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from strategist.ai.capabilities.resilience import ToolResilience
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.domain.refusal import Check, RefusalKey
from strategist.platform.refusals import (
    TOOL_REFUSALS_PER_KEY,
    KeyedRefusalToolset,
    agent_capabilities,
)
from strategist.tests._support.streamed_model import streamed
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_STEP = RefusalKey(
    check=Check.ARGUMENTS, criterion="", parameter="download.wdk_step_id"
)
_FORMAT = RefusalKey(
    check=Check.ARGUMENTS,
    criterion="wdk_step_id=7",
    parameter="download.output_format",
)


def download(
    ctx: RunContext[AgentDeps],
    wdk_step_id: Annotated[int, Field(gt=0)],
    output_format: Literal["csv", "tab"] = "csv",
) -> str:
    del ctx
    return f"{wdk_step_id}.{output_format}"


def _calls(*sent: dict[str, Any]) -> FunctionModel:
    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < len(sent):
            call = ToolCallPart("download", sent[made], f"c{made}")
            return ModelResponse(parts=[call])
        return ModelResponse(parts=[TextPart("done")])

    return streamed(_respond)


def _deps() -> AgentDeps:
    deps = agent_deps_for(
        lead_deps(pipeline_state(user_prompt="download it")), call_id="call_test"
    )
    deps.db_session_factory = None
    return deps


def _agent(model: FunctionModel, *, keyed: bool = True) -> Agent[AgentDeps, str]:
    tools = FunctionToolset([download], max_retries=3)
    toolsets = [KeyedRefusalToolset(wrapped=tools) if keyed else tools]
    return Agent(
        model,
        deps_type=AgentDeps,
        toolsets=toolsets,
        capabilities=agent_capabilities([ToolResilience()], toolsets=toolsets),
        retries=3,
    )


def _returns(messages: Sequence[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def _summaries(part: ToolReturnPart) -> list[str]:
    return [
        chunk.data["status"]
        for chunk in part.metadata or []
        if isinstance(chunk, DataChunk)
    ]


_NO_STEP = {"wdk_step_id": 0}
_NO_FORMAT = {"wdk_step_id": 7, "output_format": "xlsx"}


async def test_four_shape_errors_on_one_tool_do_not_stop_the_run() -> None:
    deps = _deps()

    result = await _agent(
        _calls(_NO_STEP, _NO_FORMAT, _NO_STEP, _NO_FORMAT, {"wdk_step_id": 7})
    ).run("download", deps=deps)

    *refused, ran = _returns(result.all_messages())
    assert [p.outcome for p in refused] == ["failed"] * 4
    assert [_summaries(p) for p in refused] == [["corrected"]] * 4
    assert ran.content == "7.csv"
    assert result.output == "done"


async def test_a_tool_outside_the_keyed_toolsets_keeps_its_own_retries() -> None:
    deps = _deps()

    with pytest.raises(UnexpectedModelBehavior, match="exceeded max retries"):
        await _agent(_calls(*[_NO_STEP] * 4), keyed=False).run("download", deps=deps)

    assert deps.refusal_book.ledger.uses == ()


async def test_a_correct_call_resets_the_shape_keys() -> None:
    deps = _deps()

    await _agent(_calls(_NO_STEP, _NO_FORMAT)).run("download", deps=deps)
    charged = (
        deps.refusal_book.ledger.used(_STEP),
        deps.refusal_book.ledger.used(_FORMAT),
    )
    await _agent(_calls({"wdk_step_id": 7})).run("download", deps=deps)

    assert charged == (1, 1)
    assert deps.refusal_book.ledger.uses == ()


async def test_a_spent_shape_key_answers_spent_and_the_run_goes_on() -> None:
    deps = _deps()

    result = await _agent(_calls(*[_NO_STEP] * 4)).run("download", deps=deps)

    *refused, spent = _returns(result.all_messages())
    assert [p.outcome for p in refused] == ["failed"] * TOOL_REFUSALS_PER_KEY
    assert (spent.outcome, _summaries(spent)) == ("failed", [])
    assert str(spent.content).startswith("No more attempts for download.wdk_step_id.")
    assert deps.refusal_book.ledger.used(_STEP) == TOOL_REFUSALS_PER_KEY
    assert result.output == "done"


async def test_every_invalid_field_is_its_own_problem() -> None:
    deps = _deps()

    result = await _agent(_calls({"wdk_step_id": -1, "output_format": "xlsx"})).run(
        "download", deps=deps
    )

    [refused] = _returns(result.all_messages())
    assert refused.content == (
        "2 problems:\n"
        "1. wdk_step_id: Input should be greater than 0 (got -1).\n"
        "2. output_format: Input should be 'csv' or 'tab' (got 'xlsx'). "
        "Nothing was recorded."
    )
    assert [use.key.parameter for use in deps.refusal_book.ledger.uses] == [
        "download.wdk_step_id",
        "download.output_format",
    ]
