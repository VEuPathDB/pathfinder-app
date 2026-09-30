"""A check reads the record of a gene its sample returned and never of a control:
a control test answers a control."""

from __future__ import annotations

import pytest
from pydantic_ai import Agent, Tool, ToolFailed
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

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.tools.standalone import gene_record
from pathfinder.ai.tools.toolsets._refusals import RefusalMemoryToolset
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.separation import AttachedControls
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_SAMPLED = "PF3D7_0102200"


def _record(gene_id: str) -> GeneRecordSummary:
    return GeneRecordSummary(
        site_id="plasmodb",
        gene_id=gene_id,
        record_url=f"https://plasmodb.org/plasmo/app/record/gene/{gene_id}",
        organism="Plasmodium falciparum 3D7",
        product="ring-infected erythrocyte surface antigen",
    )


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    async def _read(
        site_id: str, gene_id: str, *, ortholog_organism: str | None = None
    ) -> GeneRecordSummary:
        del site_id, ortholog_organism
        seen.append(gene_id)
        return _record(gene_id)

    monkeypatch.setattr(read, "read_gene_record", _read)
    return seen


async def test_a_sampled_gene_is_read(asked: list[str]) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes([_SAMPLED, "PF3D7_0935800"])

    result = await gene_record.read_sampled_gene_record(ctx, _SAMPLED)

    assert (asked, returned(result, GeneRecordSummary).gene_id) == (
        [_SAMPLED],
        _SAMPLED,
    )


async def test_a_gene_no_sample_returned_is_refused(asked: list[str]) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes([_SAMPLED])

    with pytest.raises(ToolFailed) as refused:
        await gene_record.read_sampled_gene_record(ctx, "PF3D7_1133400")

    assert (asked, refused.value.message) == (
        [],
        (
            "PF3D7_1133400 is not a gene a sample of this turn returned. A check "
            f"reads the records of its sampled genes only: {_SAMPLED}."
        ),
    )


async def test_a_sampled_gene_named_without_its_version_names_the_sampled_id(
    asked: list[str],
) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes(["LdBPK_010310.1", "LdBPK_030050.1"])

    with pytest.raises(ToolFailed) as refused:
        await gene_record.read_sampled_gene_record(ctx, "LdBPK_010310")

    assert asked == []
    assert refused.value.message.startswith(
        "LdBPK_010310 is not a gene a sample of this turn returned; the sample "
        "returned LdBPK_010310.1. Read it by that id."
    )


async def test_a_control_a_test_filed_is_refused_even_when_sampled(
    asked: list[str],
) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes([_SAMPLED])
    ctx.deps.turn_markers.record_control_tests(
        [
            ControlTestRun(
                tool_call_id="call_test",
                evidence=ControlTestEvidence(
                    tested_label="Transmembrane Domain Count",
                    positive=ControlSetEvidence(
                        returned=[_SAMPLED], not_returned=["PF3D7_1133400"]
                    ),
                ),
            )
        ]
    )

    with pytest.raises(ToolFailed) as refused:
        await gene_record.read_sampled_gene_record(ctx, _SAMPLED)

    assert (asked, refused.value.message) == (
        [],
        (
            f"{_SAMPLED} is a control. A control's record is not read; the "
            "control test states whether the strategy returned it."
        ),
    )


async def test_an_adopted_control_is_refused(asked: list[str]) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes([_SAMPLED])
    ctx.deps.verification_scope.controls = AttachedControls(
        task_id="task-1",
        control_set_id="cs-1",
        positives=[],
        negatives=[_SAMPLED],
    )

    with pytest.raises(ToolFailed):
        await gene_record.read_sampled_gene_record(ctx, _SAMPLED)

    assert asked == []


_EIGHT = [f"cgd{n}_1000" for n in range(1, 9)]


async def test_a_record_this_check_read_is_refused_naming_the_reads(
    asked: list[str],
) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes(_EIGHT[:2])
    await gene_record.read_sampled_gene_record(ctx, _EIGHT[0])

    with pytest.raises(ToolFailed) as refused:
        await gene_record.read_sampled_gene_record(ctx, _EIGHT[0])

    assert (asked, refused.value.message) == (
        [_EIGHT[0]],
        (
            f"This check already read the record of {_EIGHT[0]}; its answer is "
            f"above. The records this check read: {_EIGHT[0]}. Judge the sampled "
            "genes from those records."
        ),
    )


async def test_a_read_past_the_checks_budget_is_refused_naming_the_alternative(
    asked: list[str],
) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes([*_EIGHT, "cgd9_1000"])
    for gene_id in _EIGHT:
        await gene_record.read_sampled_gene_record(ctx, gene_id)

    with pytest.raises(ToolFailed) as refused:
        await gene_record.read_sampled_gene_record(ctx, "cgd9_1000")

    assert (len(asked), refused.value.message) == (
        8,
        (
            "This check read 8 records, the most one check reads: "
            f"{', '.join(_EIGHT)}. Judge the sampled genes from those records, "
            "and read a criterion over the whole step with read_step_columns."
        ),
    )


async def test_the_budget_belongs_to_one_check(asked: list[str]) -> None:
    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes(_EIGHT)
    await gene_record.read_sampled_gene_record(ctx, _EIGHT[0])
    ctx.deps.verification_scope.check_id = "second_check"

    result = await gene_record.read_sampled_gene_record(ctx, _EIGHT[0])

    assert (asked, returned(result, GeneRecordSummary).gene_id) == (
        [_EIGHT[0], _EIGHT[0]],
        _EIGHT[0],
    )


def _reads_of(gene_id: str, times: int) -> FunctionModel:
    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < times:
            return ModelResponse(
                parts=[ToolCallPart("read_gene_record", {"gene_id": gene_id})]
            )
        return ModelResponse(parts=[TextPart("judged")])

    return FunctionModel(respond)


async def test_a_re_read_fails_without_spending_a_retry(asked: list[str]) -> None:
    deps = agent_run_context().deps
    deps.turn_markers.record_sampled_genes(_EIGHT[:2])
    agent = Agent(
        _reads_of(_EIGHT[0], 3),
        deps_type=AgentDeps,
        toolsets=[
            RefusalMemoryToolset(
                wrapped=FunctionToolset(
                    [
                        Tool(
                            gene_record.read_sampled_gene_record,
                            name="read_gene_record",
                        )
                    ],
                    max_retries=3,
                )
            )
        ],
    )

    result = await agent.run("judge the sample", deps=deps)

    answers = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    ]
    assert asked == [_EIGHT[0]]
    assert [
        (type(p).__name__, p.outcome if isinstance(p, ToolReturnPart) else "retry")
        for p in answers
    ] == [
        ("ToolReturnPart", "success"),
        ("ToolReturnPart", "failed"),
        ("ToolReturnPart", "failed"),
    ]


async def test_a_read_the_site_did_not_answer_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unanswered(
        site_id: str, gene_id: str, *, ortholog_organism: str | None = None
    ) -> GeneRecordSummary:
        del ortholog_organism
        raise read.UnknownGeneRecordError(site_id, gene_id)

    ctx = agent_run_context()
    ctx.deps.turn_markers.record_sampled_genes(_EIGHT[:1])
    monkeypatch.setattr(read, "read_gene_record", _unanswered)

    with pytest.raises(read.UnknownGeneRecordError):
        await gene_record.read_sampled_gene_record(ctx, _EIGHT[0])
