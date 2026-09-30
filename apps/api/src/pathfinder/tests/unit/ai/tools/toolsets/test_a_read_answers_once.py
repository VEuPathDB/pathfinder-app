"""A read the wrapper lists answers each set of arguments once per run.

The same read again fails without running and names the call that answered it,
so a cycle over a few ids cannot spend the turn's budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.agents.tool_vocabulary import CHECK_READS, RECORD_READS
from pathfinder.ai.lead.lead_agent import build_lead_toolset
from pathfinder.ai.tools.toolsets import frame, verification
from pathfinder.ai.tools.toolsets._read_once import ReadOnceToolset

# The five genes the portal glycosome sample listed.
_SAMPLE = [
    "LdBPK_010310.1",
    "LdBPK_030050.1",
    "LdBPK_040440.1",
    "LdBPK_041170.1",
    "LdBPK_050090.1",
]


@dataclass
class _Deps:
    reads: list[str] = field(default_factory=list)


def read_gene_record(ctx: RunContext[_Deps], gene_id: str) -> str:
    ctx.deps.reads.append(gene_id)
    if not gene_id.endswith(".1"):
        msg = f"{gene_id} is not a gene id on this site."
        raise ModelRetry(msg)
    return f"{gene_id}: Polyphosphatase"


def think(ctx: RunContext[_Deps], note: str) -> str:
    del ctx
    return note


def _scripted(calls: list[tuple[str, dict[str, str]]]) -> FunctionModel:
    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < len(calls):
            name, args = calls[made]
            return ModelResponse(parts=[ToolCallPart(name, args, f"call_{made}")])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(respond)


def _reading() -> ReadOnceToolset[_Deps]:
    return ReadOnceToolset(
        wrapped=FunctionToolset([read_gene_record, think], max_retries=3),
        reads=frozenset({"read_gene_record"}),
    )


type _Answer = ToolReturnPart | RetryPromptPart


async def _run(
    calls: list[tuple[str, dict[str, str]]],
    toolset: ReadOnceToolset[_Deps] | None = None,
) -> tuple[_Deps, list[_Answer]]:
    deps = _Deps()
    agent = Agent(_scripted(calls), deps_type=_Deps, toolsets=[toolset or _reading()])
    result = await agent.run("show me the five genes", deps=deps)
    parts: list[_Answer] = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    ]
    return deps, parts


def _reads(*gene_ids: str) -> list[tuple[str, dict[str, str]]]:
    return [("read_gene_record", {"gene_id": g}) for g in gene_ids]


@pytest.mark.asyncio
async def test_a_cycle_over_five_ids_reads_each_record_once() -> None:
    deps, parts = await _run(_reads(*_SAMPLE, *_SAMPLE, *_SAMPLE))

    assert deps.reads == _SAMPLE
    assert [p.outcome for p in parts if isinstance(p, ToolReturnPart)] == [
        *["success"] * 5,
        *["failed"] * 10,
    ]


@pytest.mark.asyncio
async def test_the_repeat_names_the_call_that_answered_it() -> None:
    _, parts = await _run(_reads(_SAMPLE[0], _SAMPLE[0]))

    repeat = parts[1]
    assert isinstance(repeat, ToolReturnPart)
    assert repeat.outcome == "failed"
    assert repeat.content == (
        "read_gene_record already answered these arguments in this run, in call "
        'call_0 ({"gene_id": "LdBPK_010310.1"}). Read that answer; the same read '
        "does not run again."
    )


@pytest.mark.asyncio
async def test_a_refused_read_is_not_held_as_an_answer() -> None:
    deps, _ = await _run(_reads("LdBPK_010310", "LdBPK_010310"))

    assert deps.reads == ["LdBPK_010310", "LdBPK_010310"]


@pytest.mark.asyncio
async def test_a_tool_the_wrapper_does_not_list_runs_every_time() -> None:
    _, parts = await _run([("think", {"note": "a"}), ("think", {"note": "a"})])

    assert [p.outcome for p in parts if isinstance(p, ToolReturnPart)] == [
        "success",
        "success",
    ]


@pytest.mark.asyncio
async def test_another_run_answers_the_read_again() -> None:
    toolset = _reading()
    first, _ = await _run(_reads(_SAMPLE[0]), toolset)
    second, _ = await _run(_reads(_SAMPLE[0]), toolset)

    assert (first.reads, second.reads) == ([_SAMPLE[0]], [_SAMPLE[0]])


def test_the_lead_reads_each_record_once() -> None:
    toolset = build_lead_toolset()

    assert isinstance(toolset, ReadOnceToolset)
    assert toolset.reads == RECORD_READS
    assert "read_gene_record" in RECORD_READS


def test_a_check_reads_each_record_and_each_sample_once() -> None:
    toolset = verification.build_toolset()

    assert isinstance(toolset, ReadOnceToolset)
    assert toolset.reads == CHECK_READS
    assert {"get_sample_records", "get_strategy"} <= CHECK_READS
    assert RECORD_READS <= CHECK_READS


def test_a_framing_pass_reads_each_record_once() -> None:
    toolset = frame.build_toolset()

    assert isinstance(toolset, ReadOnceToolset)
    assert toolset.reads == RECORD_READS
