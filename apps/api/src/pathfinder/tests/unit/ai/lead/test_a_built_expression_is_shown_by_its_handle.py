from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic_ai.messages import ToolReturnPart
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.edit_messages import pending_lines
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.sub_agent_tools import apply_agent_state
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.tools.standalone.strategy_graph import get_strategy
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.expression_handles import expression_handle
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.question_options import SetValues, TypedOption
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import diff_specs
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.ai.tools.test_a_built_expression_binds_by_its_handle import (
    EXPRESSION,
    SEARCH,
    bind,
    built,
    framing_state,
    sheet,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import serve_search

_CASES = pytest.mark.parametrize("ceiling", [None, 1_900], ids=["recorded", "long"])
_OTHER = "APIC>=1T AND MAMM=0T"
_PROMPT = "Which comparison of protein counts do you mean?"


@pytest.fixture(autouse=True)
def _phyletic_search(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, sheet, url_segment=SEARCH, display_name="Phyletic")


async def _framed(ceiling: int | None) -> tuple[AgentToolState, str, str]:
    state = framing_state()
    handle = (await built(state, ceiling)).handle
    await bind(state, handle)
    return state, handle, state.built_expressions[handle].expression


def _domain(state: AgentToolState) -> StrategyDomainState:
    return StrategyDomainState(
        operational_spec=state.operational_spec_draft,
        built_expressions=state.built_expressions,
    )


@_CASES
async def test_the_ledger_frame_section_shows_the_handle(ceiling: int | None) -> None:
    state, handle, expression = await _framed(ceiling)

    frame = derive_ledger(
        pipeline_state("orthomcl", domain=_domain(state)), None
    ).render_section("frame")

    assert (expression[-40:] in frame, f"({EXPRESSION}) = {handle}" in frame) == (
        False,
        True,
    )


@_CASES
async def test_the_strategy_read_shows_the_handle(ceiling: int | None) -> None:
    _, handle, expression = await _framed(ceiling)
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph(graph_id="g1", name="Groups", site_id="orthomcl")
    graph.record_type = "group"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="c_more",
            search_name=SEARCH,
            parameters={EXPRESSION: StringValue(value=expression)},
        )
    )
    graph.recompute_roots()
    session.graph = graph

    result = await get_strategy(
        agent_run_context(site_id="orthomcl", strategy_session=session),
        summary_only=False,
    )

    wire = ToolReturnPart(
        tool_name="get_strategy", content=result.return_value
    ).model_response_str()
    assert (expression[-40:] in wire, handle in wire) == (False, True)


@_CASES
async def test_a_pending_edit_line_shows_both_handles(ceiling: int | None) -> None:
    state, handle, expression = await _framed(ceiling)
    planned = state.operational_spec_draft
    [criterion] = planned.criteria
    answered = OperationalSpec(
        criteria=[
            criterion.model_copy(
                update={
                    "resolved_params": {
                        EXPRESSION: criterion.resolved_params[EXPRESSION].model_copy(
                            update={"value": StringValue(value=_OTHER)}
                        )
                    }
                }
            )
        ]
    )

    lines = pending_lines(diff_specs(answered, planned), planned, answered)

    [line] = [line for line in lines if line.startswith("- [c_more]")]
    assert line == (
        f"- [c_more] states {EXPRESSION}={handle}; the strategy runs "
        f"{EXPRESSION}={expression_handle(_OTHER)}."
    )
    assert expression[-40:] not in "\n".join(lines)


@_CASES
async def test_the_facts_row_shows_the_reading(ceiling: int | None) -> None:
    state, _, expression = await _framed(ceiling)
    deps = lead_deps(pipeline_state("orthomcl", domain=_domain(state)))

    [step] = turn_facts(deps).steps
    [row] = [p for p in step.parameters if p.name == EXPRESSION]

    assert expression[-40:] not in row.value
    assert len(row.value) <= 2_000


async def test_a_card_binds_the_full_expression_its_handle_stands_for() -> None:
    state, handle, expression = await _framed(1_900)
    held = state.operational_spec_draft.model_copy(deep=True)
    [criterion] = held.criteria
    held.criteria = [
        criterion.model_copy(
            update={
                "resolved_params": {
                    EXPRESSION: criterion.resolved_params[EXPRESSION].model_copy(
                        update={"value": StringValue(value=_OTHER)}
                    )
                }
            }
        )
    ]
    question = OpenQuestion(
        question=_PROMPT,
        dimension=ConstraintKind.OTHER,
        options=[
            TypedOption(
                id="o_more",
                label="More proteins in tgon",
                binding=SetValues(criterion_id="c_more", params={EXPRESSION: handle}),
            ),
            TypedOption(
                id="o_only",
                label="Only in Apicomplexa",
                binding=SetValues(criterion_id="c_more", params={EXPRESSION: _OTHER}),
            ),
        ],
    )
    pipeline = pipeline_state(
        "orthomcl",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=held,
            open_questions=[question],
            built_expressions=state.built_expressions,
        ),
    )

    apply_option_bindings(
        pipeline,
        [
            UserQuestionAnswer(
                question_id="q1",
                prompt=_PROMPT,
                chosen_labels=["More proteins in tgon"],
            )
        ],
        sheets={SEARCH: sheet({})},
    )

    spec = pipeline.domain.operational_spec
    assert spec is not None
    assert spec.criteria[0].resolved_params[EXPRESSION].value.to_wire() == expression
    [step] = turn_facts(lead_deps(pipeline)).steps
    [row] = [p for p in step.parameters if p.name == EXPRESSION]
    shown = "\n".join([row.value, row.label, *row.notes])
    assert (len(expression), expression[-40:] in shown) == (50_979, False)
    assert max(len(row.value), *(len(note) for note in row.notes)) <= 2_100


async def test_a_built_expression_lives_as_long_as_the_conversation() -> None:
    state, handle, expression = await _framed(None)
    pipeline = pipeline_state("orthomcl", domain=StrategyDomainState())
    deps = lead_deps(pipeline)
    agent_deps = agent_deps_for(deps, call_id="call_test")
    agent_deps.agent_state.built_expressions.update(state.built_expressions)

    apply_agent_state(deps, agent_deps)

    assert pipeline.domain.built_expressions == state.built_expressions
    assert agent_deps_for(deps, call_id="call_test").agent_state.built_expressions == {
        handle: state.built_expressions[handle]
    }
    assert state.built_expressions[handle].expression == expression
