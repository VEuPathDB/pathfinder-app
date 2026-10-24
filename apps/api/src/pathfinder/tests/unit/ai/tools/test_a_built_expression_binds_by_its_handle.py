from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ToolReturn, ToolReturnPart
from veupathdb_mcp.catalog import ParameterInfo, PhyleticPattern

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    BuiltExpression,
    build_phyletic_expression,
)
from pathfinder.domain.strategy.expression_handles import expression_handle
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.orthomcl_counts import (
    LADDER,
    SITE,
    CountsBelow,
    replayed_counts,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._rationale_catalog import choice
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    param_info,
    serve_search,
)

SEARCH = "GroupsByPhyleticPattern"
EXPRESSION = "phyletic_expression"
TEXT = "groups with more proteins in tgon than in pfal"
_PATTERN: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)
MORE_IN_TGON = _PATTERN.validate_python(
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["tgon"]},
        "right": {"kind": "codes", "codes": ["pfal"]},
        "reading": "totals",
        "condition": "more_than",
    }
)
_WIRE_CEILING = 4_000


def sheet(context: dict[str, str]) -> list[ParameterInfo]:
    del context
    return [param_info(EXPRESSION, display_name="Expression")]


def framing_state() -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(listing([SEARCH]))
    state.request_messages = [TEXT]
    return state


async def built(state: AgentToolState, ceiling: int | None) -> BuiltExpression:
    with replayed_counts(LADDER) as replay:
        if ceiling is not None:
            replay.totals = CountsBelow(ceiling)
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE, agent_state=state), MORE_IN_TGON
        )
    return returned(result, BuiltExpression)


def model_text(result: ToolReturn[Any], tool_name: str) -> str:
    return ToolReturnPart(
        tool_name=tool_name, content=result.return_value
    ).model_response_str()


async def bind(state: AgentToolState, value: str) -> ToolReturn[SetCriterionResult]:
    return await set_criterion(
        frame_ctx(state),
        criterion_id="c_more",
        text=TEXT,
        search_name=SEARCH,
        params={EXPRESSION: value},
        why=choice("parameter", "Expression", "the expression states the request"),
    )


@pytest.fixture(autouse=True)
def _phyletic_search(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, sheet, url_segment=SEARCH, display_name="Phyletic")


@pytest.mark.parametrize(
    ("ceiling", "length"), [(None, 2_690), (3_000, 81_779)], ids=["recorded", "long"]
)
async def test_no_return_of_a_bind_by_handle_carries_the_expression(
    ceiling: int | None, length: int
) -> None:
    state = framing_state()
    handle = (await built(state, ceiling)).handle
    expression = state.built_expressions[handle].expression

    result = await bind(state, handle)

    [criterion] = state.operational_spec_draft.criteria
    wire = model_text(result, "set_criterion")
    assert (len(expression), handle) == (length, expression_handle(expression))
    assert criterion.resolved_params[EXPRESSION].value.to_wire() == expression
    assert (expression[-40:] in wire, len(wire) < _WIRE_CEILING) == (False, True)
    assert returned(result, SetCriterionResult).resolved_params == {EXPRESSION: handle}


async def test_the_builder_returns_the_handle_and_keeps_the_expression() -> None:
    state = framing_state()

    handle = (await built(state, 3_000)).handle

    [(held_handle, held)] = state.built_expressions.items()
    assert (held_handle, len(held.expression), held.pattern) == (
        handle,
        81_779,
        MORE_IN_TGON,
    )


async def test_an_unknown_handle_is_refused_by_name() -> None:
    state = framing_state()

    with pytest.raises(ModelRetry) as refused:
        await bind(state, "expr:0123456789ab")

    assert str(refused.value) == (
        "phyletic_expression names expr:0123456789ab, and no expression of this "
        "conversation is held under that handle: neither build_phyletic_expression "
        "nor a bound criterion wrote it. Call build_phyletic_expression and bind "
        "the handle it returns; nothing was recorded."
    )
    assert state.operational_spec_draft.criteria == []


async def test_a_short_typed_expression_binds_as_written() -> None:
    state = framing_state()

    result = await bind(state, "APIC>=1T AND MAMM=0T")

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.resolved_params[EXPRESSION].value.to_wire() == (
        "APIC>=1T AND MAMM=0T"
    )
    assert returned(result, SetCriterionResult).resolved_params == {
        EXPRESSION: expression_handle("APIC>=1T AND MAMM=0T")
    }
