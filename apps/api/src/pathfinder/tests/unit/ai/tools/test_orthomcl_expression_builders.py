from __future__ import annotations

import pytest
from pydantic import JsonValue, TypeAdapter
from pydantic_ai import ModelRetry, ToolFailed
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb import JSONObject
from veupathdb.domain.parameters import PhyleticExpression
from veupathdb.wdk import get_site
from veupathdb_mcp import MAX_CALL_SECONDS_META_KEY
from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.server import TOOLS

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.tools.standalone import orthomcl_expressions
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    BuiltExpression,
    build_phyletic_expression,
)
from pathfinder.ai.tools.toolsets.frame import build_toolset
from pathfinder.domain.strategy.expression_handles import expression_handle
from pathfinder.tests._support.orthomcl_counts import (
    CLADE_ONLY,
    CRYPTOSPORIDIUM,
    EVERY_SPECIES,
    LADDER,
    SITE,
    replayed_counts,
)
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context, summary_of

_PATTERN: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)
_COUNT_REPORT = "/record-types/group/searches/GroupsByPhyleticPattern/reports/standard"
_MORE_IN_TGON: JSONObject = {
    "kind": "compare",
    "left": {"kind": "codes", "codes": ["tgon"]},
    "right": {"kind": "codes", "codes": ["pfal"]},
    "reading": "totals",
    "condition": "more_than",
}
_ONLY_IN_APIC: JSONObject = {
    "kind": "all_of",
    "terms": [
        {
            "kind": "count",
            "of": {"kind": "codes", "codes": ["APIC"]},
            "measure": "genomes",
            "condition": "at_least",
            "value": 1,
        },
        {
            "kind": "count",
            "of": {"kind": "all_except", "codes": ["APIC"]},
            "condition": "absent",
        },
    ],
}
_CRYPTOSPORIDIUM_CODES: list[JsonValue] = [*CRYPTOSPORIDIUM]
_EVERY_CRYPTOSPORIDIUM_SPECIES: JSONObject = {
    "kind": "count",
    "of": {"kind": "each_species_of", "codes": _CRYPTOSPORIDIUM_CODES},
    "measure": "share",
    "condition": "at_least",
    "value": 50,
}


async def _built(raw: JSONObject) -> tuple[BuiltExpression, str]:
    state = AgentToolState()
    result = await build_phyletic_expression(
        agent_run_context(site_id=SITE, agent_state=state),
        _PATTERN.validate_python(raw),
    )
    built = returned(result, BuiltExpression)
    return built, state.built_expressions[built.handle].expression


async def test_a_comparison_reads_the_largest_count_and_counts_the_recorded_groups() -> (
    None
):
    state = AgentToolState()
    with replayed_counts(LADDER) as replay:
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE, agent_state=state),
            _PATTERN.validate_python(_MORE_IN_TGON),
        )

    built = returned(result, BuiltExpression)
    assert (built.handle, built.groups, len(replay.sent)) == (
        expression_handle(replay.sent[-1]),
        3896,
        9,
    )
    assert state.built_expressions[built.handle].expression == replay.sent[-1]
    assert sorted(built.codes) == ["pfal", "tgon"]
    assert summary_of(result).data["summary"] == "3896 groups"


async def test_presence_only_in_a_clade_is_one_count_read() -> None:
    with replayed_counts(CLADE_ONLY) as replay:
        built, expression = await _built(_ONLY_IN_APIC)

    assert built.groups == 54039
    assert replay.sent == [expression]
    assert "APIC" in PhyleticExpression.parse(expression).codes()


async def test_presence_in_every_species_counts_each_species_at_half_its_genomes() -> (
    None
):
    with replayed_counts(EVERY_SPECIES) as replay:
        built, expression = await _built(_EVERY_CRYPTOSPORIDIUM_SPECIES)

    assert built.groups == 2505
    assert replay.sent == [expression]
    assert sorted(built.codes) == sorted(CRYPTOSPORIDIUM)


async def test_a_code_the_taxonomy_lacks_is_sent_back_before_any_count() -> None:
    absent: JSONObject = {
        "kind": "count",
        "of": {"kind": "codes", "codes": ["NOPE"]},
        "condition": "absent",
    }

    with replayed_counts(CLADE_ONLY) as replay, pytest.raises(ModelRetry) as refused:
        await _built(absent)

    assert str(refused.value) == (
        "build_phyletic_expression refused the pattern before the site ran it: "
        "These codes are not in the site's taxonomy: ['NOPE']. This is the "
        "builder's own limit, not a site failure: correct or narrow the pattern and "
        "build it again. A requirement no pattern within the limit states is never "
        "site_refused_the_search."
    )
    assert replay.sent == []


def test_the_builder_keeps_the_budget_the_served_tool_declares() -> None:
    [served] = [
        row.meta for row in TOOLS if row.fn.__name__ == "build_phyletic_expression"
    ]

    assert served == {
        MAX_CALL_SECONDS_META_KEY: orthomcl_expressions.PHYLETIC_EXPRESSION_MAX_CALL_SECONDS
    }
    assert orthomcl_expressions.PHYLETIC_EXPRESSION_MAX_CALL_SECONDS == 300


async def test_the_site_comes_from_the_turn_and_the_model_states_only_the_pattern() -> (
    None
):
    tools = await build_toolset().get_tools(agent_run_context(site_id=SITE))
    schema = tools["build_phyletic_expression"].tool_def.parameters_json_schema

    assert (sorted(schema["properties"]), schema["required"]) == (
        ["pattern"],
        ["pattern"],
    )


async def test_a_count_report_the_site_fails_is_a_failed_call_the_model_reads() -> None:
    report = f"{get_site(SITE).service_url}{_COUNT_REPORT}"

    with (
        replayed_counts(LADDER, status=503) as replay,
        pytest.raises(ToolFailed) as failed,
    ):
        await _built(_MORE_IN_TGON)

    assert str(failed.value) == (
        "build_phyletic_expression got no answer from the site (HTTP 503: "
        "VEuPathDB service error: Request failed after retries: Server error "
        f"'503 Service Unavailable' for url '{report}'\nFor more "
        "information check: "
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/503). Nothing "
        "was read and the strategy is unchanged. Say that the site did not answer "
        "this read, and answer from what the turn already holds."
    )
    assert replay.sent == ["pfal>=128"]


async def test_a_build_past_its_budget_is_a_failed_call_the_model_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orthomcl_expressions, "PHYLETIC_EXPRESSION_MAX_CALL_SECONDS", 0.01
    )

    with (
        replayed_counts(LADDER, delay=1.0) as replay,
        pytest.raises(ToolFailed) as failed,
    ):
        await _built(_MORE_IN_TGON)

    assert str(failed.value) == (
        "build_phyletic_expression got no answer from the site (no answer within "
        "0.01 s for the phyletic expression's group counts). Nothing was read and "
        "the strategy is unchanged. Say that the site did not answer this read, "
        "and answer from what the turn already holds."
    )
    assert replay.sent == []


async def test_frame_reads_the_built_expression_as_its_tool_result() -> None:
    returns: list[ToolReturnPart] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        returns.extend(p for p in last.parts if isinstance(p, ToolReturnPart))
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "build_phyletic_expression",
                        {"pattern": _ONLY_IN_APIC},
                        "call_pattern",
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result",
                    {"summary": "Built the pattern.", "disposition": "needs_research"},
                )
            ]
        )

    agent = build_frame_agent()
    with (
        replayed_counts(CLADE_ONLY) as replay,
        agent.override(model=FunctionModel(_frame, model_name="scripted")),
    ):
        run = await agent.run(
            "FRAME work order: frame it", deps=agent_run_context(site_id=SITE).deps
        )

    assert isinstance(run.output, FrameResult)
    [answer] = returns
    built = BuiltExpression.model_validate(answer.content)
    assert answer.tool_name == "build_phyletic_expression"
    assert (built.handle, built.groups, len(replay.sent)) == (
        expression_handle(replay.sent[0]),
        54039,
        1,
    )
    assert replay.sent[0] not in answer.model_response_str()
