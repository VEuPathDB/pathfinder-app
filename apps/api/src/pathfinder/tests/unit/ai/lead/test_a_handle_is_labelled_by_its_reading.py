from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_requirements import questions_for_the_card
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.expression_handles import READING_LIMIT
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.question_options import SetValues
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.test_a_built_expression_binds_by_its_handle import (
    EXPRESSION,
    SEARCH,
    bind,
    built,
    framing_state,
    sheet,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import serve_search

_PROMPT = "Which comparison of protein counts do you mean?"


@pytest.fixture(autouse=True)
def _phyletic_search(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, sheet, url_segment=SEARCH, display_name="Phyletic")


async def _two_built() -> tuple[AgentToolState, str, str]:
    state = framing_state()
    long = (await built(state, 1_900)).handle
    short = (await built(state, None)).handle
    await bind(state, short)
    return state, long, short


def _shown_well(text: str, state: AgentToolState) -> bool:
    fragments = [held.expression[-40:] for held in state.built_expressions.values()]
    return (
        "expr:" not in text
        and all(fragment not in text for fragment in fragments)
        and len(text) <= READING_LIMIT + 100
    )


def _domain(state: AgentToolState, spec: OperationalSpec) -> StrategyDomainState:
    return StrategyDomainState(
        operational_spec=spec, built_expressions=state.built_expressions
    )


async def test_a_card_option_naming_a_handle_is_labelled_by_its_reading() -> None:
    state, long, short = await _two_built()
    deps = lead_deps(
        pipeline_state("orthomcl", domain=_domain(state, state.operational_spec_draft))
    )
    asked = FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question=_PROMPT,
                dimension=ConstraintKind.OTHER,
                recommended_value=long,
                criterion_id="c_more",
                param_name=EXPRESSION,
                options=[long, short],
            )
        ],
    )

    [question] = questions_for_the_card(deps, asked, [])

    labels = [option.label for option in question.options]
    assert [all(_shown_well(label, state) for label in labels), len(labels)] == [
        True,
        2,
    ]
    assert labels[0].startswith(
        f"Expression {state.built_expressions[long].reading[:40]}"
    )


async def test_the_facts_row_shows_the_reading_of_a_card_bound_handle() -> None:
    state, long, _ = await _two_built()
    spec = state.operational_spec_draft
    asked = SlotQuestion(
        question=_PROMPT,
        dimension=ConstraintKind.OTHER,
        recommended_value=long,
        criterion_id="c_more",
        param_name=EXPRESSION,
        options=[long, "APIC>=1T AND MAMM=0T"],
    )
    pipeline = pipeline_state(
        "orthomcl",
        user_message_id=uuid4(),
        domain=_domain(state, spec).model_copy(
            update={"open_questions": [asked.typed(spec.criteria[0])]}
        ),
    )
    [option] = [
        o
        for o in pipeline.domain.open_questions[0].options
        if o.binding == SetValues(criterion_id="c_more", params={EXPRESSION: long})
    ]

    apply_option_bindings(
        pipeline,
        [
            UserQuestionAnswer(
                question_id="q1", prompt=_PROMPT, chosen_labels=[option.label]
            )
        ],
        sheets={SEARCH: sheet({})},
    )

    [step] = turn_facts(lead_deps(pipeline)).steps
    [row] = [p for p in step.parameters if p.name == EXPRESSION]
    bound = pipeline.domain.operational_spec
    assert bound is not None
    assert bound.criteria[0].resolved_params[EXPRESSION].value == StringValue(
        value=state.built_expressions[long].expression
    )
    assert row.value == state.built_expressions[long].reading
    assert all(_shown_well(text, state) for text in [row.value, *row.notes])
