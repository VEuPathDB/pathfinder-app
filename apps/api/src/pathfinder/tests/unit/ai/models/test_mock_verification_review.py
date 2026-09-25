"""The mock VERIFY samples the root the work order names, reads each sampled
gene's record, and returns a review built from those reads."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from assistant_core.models.scripted import current_scope_id, current_user_text
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.models.mock import PATHFINDER_SCRIPT
from pathfinder.services.gene_records.read import GeneRecordSummary

_ORDER = (
    "Verification work order: mock verification\n"
    "Inspect the built strategy. Return a VerificationDelta.\n"
    "The root is step_a1b2c3d4, step 440299573 on the site, 5,512 records. "
    "Sample it with get_sample_records(wdk_step_id=440299573, limit=8)."
)
_SAMPLED = ("PF3D7_0100100", "PF3D7_0100200")


@pytest.fixture(autouse=True)
def _scoped() -> Generator[None]:
    text_token = current_user_text.set("create step")
    scope_token = current_scope_id.set("plasmodb")
    yield
    current_user_text.reset(text_token)
    current_scope_id.reset(scope_token)


def _info() -> AgentInfo:
    return AgentInfo(
        function_tools=[
            ToolDefinition(name=name)
            for name in ("run_control_tests_on_step", "get_sample_records")
        ],
        allow_text_output=False,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


def _call(messages: list[ModelMessage]) -> ToolCallPart:
    part = PATHFINDER_SCRIPT.response_part(messages, _info())
    assert isinstance(part, ToolCallPart)
    return part


def _answered(tool: str, content: object, call_id: str) -> list[ModelMessage]:
    return [
        ModelResponse(
            parts=[ToolCallPart(tool_name=tool, args={}, tool_call_id=call_id)]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name=tool, content=content, tool_call_id=call_id)
            ]
        ),
    ]


def _head() -> list[ModelMessage]:
    return [ModelRequest(parts=[UserPromptPart(content=_ORDER)])]


def _sampled() -> list[ModelMessage]:
    sample = SampleRecordsResult(
        step_id=440299573,
        total_count=5512,
        records=[{"id": f"{gene_id}.1"} for gene_id in _SAMPLED],
    )
    return [*_head(), *_answered("get_sample_records", sample, "call_sample")]


def _record(gene_id: str) -> GeneRecordSummary:
    """A record as plasmodb states it, the organism in the site's own markup."""
    return GeneRecordSummary(
        site_id="plasmodb",
        gene_id=gene_id,
        record_url=f"https://plasmodb.org/plasmo/app/record/gene/{gene_id}",
        organism="<i>P. falciparum 3D7</i>",
        product="conserved Plasmodium protein, unknown function",
    )


def test_the_root_the_work_order_names_is_sampled_first() -> None:
    call = _call(_head())

    assert (call.tool_name, call.args_as_dict()) == (
        "get_sample_records",
        {"wdk_step_id": 440299573, "limit": 2},
    )


def test_each_sampled_gene_is_read_once() -> None:
    first = _call(_sampled())
    read_one = [
        *_sampled(),
        *_answered("read_gene_record", _record(_SAMPLED[0]), "call_read_1"),
    ]
    second = _call(read_one)

    assert [(c.tool_name, c.args_as_dict()) for c in (first, second)] == [
        ("read_gene_record", {"gene_id": "PF3D7_0100100"}),
        ("read_gene_record", {"gene_id": "PF3D7_0100200"}),
    ]


def test_the_digest_reviews_the_genes_it_read() -> None:
    messages = [
        *_sampled(),
        *_answered("read_gene_record", _record(_SAMPLED[0]), "call_read_1"),
        *_answered("read_gene_record", _record(_SAMPLED[1]), "call_read_2"),
    ]

    final = _call(messages)
    review = VerificationDelta.model_validate(final.args_as_dict()).digest.review

    assert final.tool_name == "final_result"
    assert [(g.gene_id, g.fits) for g in review.sampled_genes] == [
        ("PF3D7_0100100", "yes"),
        ("PF3D7_0100200", "yes"),
    ]
    assert [(r.text, r.answered_by, r.status) for r in review.requirements] == [
        ("Plasmodium falciparum 3D7", ["step_a1b2c3d4"], "met")
    ]
