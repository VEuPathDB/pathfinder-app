"""A read sent again with the same arguments runs once while nothing changes."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from assistant_core.conversation.history import elide_consumed
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset

from strategist.ai.agents.tool_vocabulary import (
    CHECK_READS,
    READ_ONLY_TOOLS,
    RECORD_READS,
)
from strategist.ai.explore.explore_agent import build_explore_toolset
from strategist.ai.lead.lead_agent import build_lead_toolset
from strategist.ai.tools.toolsets import execution, frame, verification
from strategist.ai.tools.toolsets._read_once import ReadOnceToolset
from strategist.platform.refusals import KeyedRefusalToolset

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


def get_search_overview(ctx: RunContext[_Deps], search_name: str) -> str:
    ctx.deps.reads.append(search_name)
    return f"{search_name}: " + "parameter " * 60


def _reading() -> ReadOnceToolset[_Deps]:
    return ReadOnceToolset(
        wrapped=FunctionToolset(
            [read_gene_record, get_search_overview, think], max_retries=3
        ),
        reads=frozenset({"get_search_overview"}),
        lasting=frozenset({"read_gene_record"}),
    )


async def _run(
    calls: list[tuple[str, dict[str, str]]],
    toolset: ReadOnceToolset[_Deps] | None = None,
    *,
    elided: bool = False,
) -> tuple[_Deps, list[ToolReturnPart]]:
    deps = _Deps()
    agent = Agent(
        _scripted(calls),
        deps_type=_Deps,
        toolsets=[toolset or _reading()],
        capabilities=[ProcessHistory[_Deps](elide_consumed)] if elided else [],
    )
    result = await agent.run("show me the five genes", deps=deps)
    parts: list[ToolReturnPart] = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
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
        'read_gene_record answered these arguments in call call_0 ({"gene_id": '
        '"LdBPK_010310.1"}), and nothing has changed since, so it did not run '
        "again and cost nothing. Read that answer above."
    )


def _overviews(*names: str) -> list[tuple[str, dict[str, str]]]:
    return [("get_search_overview", {"search_name": n}) for n in names]


_SEARCHES = [f"GenesBySearch{i}" for i in range(12)]


@pytest.mark.asyncio
async def test_a_repeat_of_an_elided_answer_carries_the_answer_again() -> None:
    deps, parts = await _run(_overviews(*_SEARCHES, _SEARCHES[0]), elided=True)

    repeat = parts[-1]
    assert deps.reads == _SEARCHES
    assert repeat.outcome == "failed"
    assert repeat.content == (
        'get_search_overview answered these arguments in call call_0 ({"search_name": '
        '"GenesBySearch0"}), and nothing has changed since, so it did not run again '
        "and cost nothing. That answer is no longer shown above; it is: "
        '"GenesBySearch0: ' + "parameter " * 60 + '"'
    )


@pytest.mark.asyncio
async def test_a_repeat_spends_no_tool_call_of_the_budget() -> None:
    deps = _Deps()
    agent = Agent(
        _scripted(_overviews("GenesByText", "GenesByText", "GenesByText")),
        deps_type=_Deps,
        toolsets=[_reading()],
    )

    result = await agent.run("read it", deps=deps)

    assert (deps.reads, result.usage().tool_calls) == (["GenesByText"], 1)


@pytest.mark.asyncio
async def test_a_write_lets_a_read_run_again_and_a_record_stays_held() -> None:
    deps, _ = await _run(
        [
            *_overviews("GenesByText"),
            *_reads(_SAMPLE[0]),
            ("think", {"note": "a"}),
            *_overviews("GenesByText"),
            *_reads(_SAMPLE[0]),
        ]
    )

    assert deps.reads == ["GenesByText", _SAMPLE[0], "GenesByText"]


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


def test_the_lead_holds_every_read() -> None:
    keyed = build_lead_toolset()

    assert isinstance(keyed, KeyedRefusalToolset)
    toolset = keyed.wrapped
    assert isinstance(toolset, ReadOnceToolset)
    assert (toolset.reads, toolset.lasting) == (READ_ONLY_TOOLS, RECORD_READS)
    assert "read_gene_record" in RECORD_READS


def test_explore_holds_every_read() -> None:
    keyed = build_explore_toolset()

    assert isinstance(keyed, KeyedRefusalToolset)
    toolset = keyed.wrapped
    assert isinstance(toolset, ReadOnceToolset)
    assert (toolset.reads, toolset.lasting) == (READ_ONLY_TOOLS, RECORD_READS)
    assert {"get_search_overview", "get_parameter_options"} <= READ_ONLY_TOOLS


def test_a_check_reads_each_record_and_each_sample_once() -> None:
    keyed = verification.build_toolset()

    assert isinstance(keyed, KeyedRefusalToolset)
    toolset = keyed.wrapped
    assert isinstance(toolset, ReadOnceToolset)
    assert (toolset.reads, toolset.lasting) == (READ_ONLY_TOOLS, CHECK_READS)
    assert {"get_sample_records", "get_strategy"} <= CHECK_READS
    assert RECORD_READS <= CHECK_READS


def test_a_framing_pass_holds_every_read() -> None:
    keyed = frame.build_toolset()

    assert isinstance(keyed, KeyedRefusalToolset)
    toolset = keyed.wrapped
    assert isinstance(toolset, ReadOnceToolset)
    assert (toolset.reads, toolset.lasting) == (READ_ONLY_TOOLS, RECORD_READS)


def test_a_build_pass_holds_every_read() -> None:
    keyed = execution.build_toolset()

    assert isinstance(keyed, KeyedRefusalToolset)
    toolset = keyed.wrapped
    assert isinstance(toolset, ReadOnceToolset)
    assert (toolset.reads, toolset.lasting) == (READ_ONLY_TOOLS, RECORD_READS)
