from __future__ import annotations

import json
from collections.abc import Mapping

import pytest
from pydantic import TypeAdapter
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import ParamKind, ParamValue, from_wire
from veupathdb_mcp.catalog import PhyleticPattern, ValidatedParams

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.frame_option_checks import hold_an_option_to_its_parameter
from pathfinder.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    expression_handle,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.services.strategies import reading_check
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "phyletic_expression"
_EXPRESSION_LABEL = "Keep the 2-5 Plasmodium-copy criterion only"
_FILTER_LABEL = "Low nucleotide diversity per CDS site"
_FILTER_VALUE = '{"filters": [{"field": "sex", "value": ["female"]}]}'
_NO_FILTER = '{"filters": []}'
_TYPED_EXPRESSION = "APIC>=1T AND MAMM=0T"
_VALUES: dict[ParamKind, tuple[str, str]] = {
    "filter": (_FILTER_VALUE, _NO_FILTER),
    "number-range": ('{"min": 1, "max": 1}', '{"min": 3}'),
    "date-range": (
        '{"min": "2020-01-01", "max": "2021-06-30"}',
        '{"min": "2020-01-01"}',
    ),
    "number": ("1", "80"),
}
_NOT_VALUES: list[tuple[ParamKind, str]] = [
    ("filter", _FILTER_LABEL),
    ("filter", '["sex"]'),
    ("filter", '{"filters": "sex"}'),
    ("number-range", _FILTER_LABEL),
    ("number-range", "5"),
    ("number-range", '{"min": 5, "max": 1}'),
    ("date-range", _FILTER_LABEL),
    ("date-range", "[]"),
    ("date-range", '{"min": "last spring"}'),
    ("number", _FILTER_LABEL),
]


def _criterion(kind: ParamKind, param: str = "the_param") -> Criterion:
    return Criterion(
        id="c_one",
        text="one property",
        search_name="SomeSearch",
        open_params=[OpenSlot(criterion_id="c_one", param_name=param, param_kind=kind)],
    )


def _context(criterion: Criterion, *, refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    state = ctx.deps.agent_state
    state.operational_spec_draft = OperationalSpec(criteria=[criterion])
    state.refusals = refusals
    return ctx


def _question(*options: str, param: str = "the_param") -> SlotQuestion:
    return SlotQuestion(
        question="Which value do you mean?",
        dimension=ConstraintKind.UNTYPED,
        recommended_value=options[0],
        criterion_id="c_one",
        param_name=param,
        options=list(options),
    )


def _asked(question: SlotQuestion) -> FrameResult:
    return FrameResult(disposition="needs_user", open_questions=[question])


@pytest.mark.parametrize(("kind", "offered"), _NOT_VALUES)
def test_an_option_its_kind_cannot_read_is_sent_back(
    kind: ParamKind, offered: str
) -> None:
    ctx = _context(_criterion(kind))

    with pytest.raises(ModelRetry) as sent_back:
        hold_an_option_to_its_parameter(
            ctx, _asked(_question(_VALUES[kind][0], offered))
        )

    assert str(sent_back.value) == (
        f"c_one.the_param offered a value the card cannot bind: {offered!r} is not a "
        f"value of the_param: it takes a {kind} value. An option binds its value as "
        "written. Offer values this parameter takes, or ask in free text: leave "
        "`options` empty and the researcher answers in words."
    )
    assert ctx.deps.agent_state.refusals == 1


def test_a_label_on_an_expression_parameter_is_sent_back_with_the_grammar_fault() -> (
    None
):
    ctx = _context(_criterion("string", _EXPRESSION))

    with pytest.raises(ModelRetry) as sent_back:
        hold_an_option_to_its_parameter(
            ctx,
            _asked(_question(_TYPED_EXPRESSION, _EXPRESSION_LABEL, param=_EXPRESSION)),
        )

    told = str(sent_back.value)
    assert f"{_EXPRESSION_LABEL!r} is not a value of {_EXPRESSION}" in told
    assert "'Keep' needs an operator and a count" in told
    assert "ask in free text" in told


def test_a_count_the_expression_model_cannot_hold_is_sent_back() -> None:
    offered = f"APIC>={'9' * 5000}T"
    ctx = _context(_criterion("string", _EXPRESSION))

    with pytest.raises(ModelRetry, match="is not a value of phyletic_expression"):
        hold_an_option_to_its_parameter(
            ctx, _asked(_question(_TYPED_EXPRESSION, offered, param=_EXPRESSION))
        )


@pytest.mark.parametrize("kind", list(_VALUES))
def test_options_the_kind_reads_pass(kind: ParamKind) -> None:
    asked = _asked(_question(*_VALUES[kind]))
    ctx = _context(_criterion(kind))

    assert hold_an_option_to_its_parameter(ctx, asked) == asked
    assert ctx.deps.agent_state.refusals == 0


def test_a_typed_expression_and_a_handle_pass() -> None:
    asked = _asked(
        _question(
            _TYPED_EXPRESSION,
            expression_handle(_TYPED_EXPRESSION),
            param=_EXPRESSION,
        )
    )

    held = hold_an_option_to_its_parameter(
        _context(_criterion("string", _EXPRESSION)), asked
    )

    assert held == asked


def test_a_held_handle_is_read_as_its_expression() -> None:
    handle = expression_handle(_TYPED_EXPRESSION)
    ctx = _context(_criterion("string", _EXPRESSION))
    ctx.deps.agent_state.built_expressions[handle] = BuiltPattern(
        expression=_TYPED_EXPRESSION,
        pattern=TypeAdapter(PhyleticPattern).validate_python(
            {
                "kind": "count",
                "of": {"kind": "codes", "codes": ["APIC"]},
                "condition": "absent",
            }
        ),
        reading="absent from APIC",
    )
    asked = _asked(_question(handle, "MAMM>=1T", param=_EXPRESSION))

    assert hold_an_option_to_its_parameter(ctx, asked) == asked


def test_a_label_on_a_held_filter_value_is_sent_back() -> None:
    criterion = Criterion(
        id="c_one",
        text="one property",
        search_name="SomeSearch",
        resolved_params={
            "the_param": BoundValue(
                value=from_wire("filter", _NO_FILTER), source="default"
            )
        },
    )

    with pytest.raises(ModelRetry, match="is not a value of the_param"):
        hold_an_option_to_its_parameter(
            _context(criterion), _asked(_question(_FILTER_VALUE, _FILTER_LABEL))
        )


def test_a_slot_of_the_spec_names_the_kind_too() -> None:
    criterion = Criterion(id="c_one", text="one property", search_name="SomeSearch")
    ctx = _context(criterion)
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=[criterion],
        open_slots=[
            OpenSlot(criterion_id="c_one", param_name="the_param", param_kind="filter")
        ],
    )

    with pytest.raises(ModelRetry, match="is not a value of the_param"):
        hold_an_option_to_its_parameter(
            ctx, _asked(_question(_FILTER_VALUE, _FILTER_LABEL))
        )


@pytest.mark.parametrize(
    ("kind", "told"),
    [
        ("filter", "only a free-text or range parameter takes readings"),
        ("number-range", "'a few copies' is not a value of the_param"),
        ("date-range", "'a few copies' is not a value of the_param"),
        ("number", "'a few copies' is not a value of the_param"),
    ],
)
async def test_a_reading_its_kind_cannot_read_is_sent_back_and_raises_nothing_else(
    kind: ParamKind, told: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)
    question = SlotQuestion(
        question="Which one do you mean?",
        recommended_value="The first",
        criterion_id="c_one",
        param_name="the_param",
        readings=[
            Reading(label="The first", value=_VALUES[kind][0]),
            Reading(label="The second", value=_VALUES[kind][1]),
            Reading(label="A few", value="a few copies"),
        ],
    )
    criterion = _criterion(kind).model_copy(update={"record_class": "transcript"})

    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_readings_to_the_site(_context(criterion), _asked(question))

    assert told in str(sent_back.value)


def test_options_beside_readings_are_the_reading_check_s_to_refuse() -> None:
    question = _question(_FILTER_LABEL, "Another label").model_copy(
        update={
            "readings": [
                Reading(label="None", value=_NO_FILTER),
                Reading(label="Some", value=_FILTER_VALUE),
            ]
        }
    )
    asked = _asked(question)

    assert (
        hold_an_option_to_its_parameter(_context(_criterion("filter")), asked) == asked
    )


@pytest.mark.parametrize(
    "kind", ["string", "single-pick-vocabulary", "multi-pick-vocabulary"]
)
def test_a_kind_that_takes_any_word_passes_a_word(kind: ParamKind) -> None:
    asked = _asked(_question("Pf3D7", "PvP01"))

    assert hold_an_option_to_its_parameter(_context(_criterion(kind)), asked) == asked


def test_a_question_that_names_no_slot_passes() -> None:
    asked = _asked(
        SlotQuestion(
            question="Which value do you mean?",
            recommended_value=_FILTER_LABEL,
            options=[_FILTER_LABEL, "Another label"],
        )
    )

    assert (
        hold_an_option_to_its_parameter(_context(_criterion("filter")), asked) == asked
    )


def test_a_hidden_parameter_binds_nothing_so_it_refuses_nothing() -> None:
    criterion = Criterion(
        id="c_one",
        text="one property",
        search_name="SomeSearch",
        resolved_params={
            "the_param": BoundValue(
                value=from_wire("filter", _NO_FILTER),
                source="default",
                visible=False,
            )
        },
    )
    asked = _asked(_question(_FILTER_LABEL, "Another label"))

    assert hold_an_option_to_its_parameter(_context(criterion), asked) == asked


def test_a_parked_run_is_no_result_to_check() -> None:
    parked = DeferredToolRequests()

    assert (
        hold_an_option_to_its_parameter(_context(_criterion("filter")), parked)
        is parked
    )


def test_at_the_bound_the_question_asks_in_free_text_with_a_named_gap() -> None:
    other = SlotQuestion(
        question="Which other value?",
        recommended_value="1",
        criterion_id="c_one",
        param_name="the_other",
        options=["1", "2"],
    )
    question = _question(_FILTER_VALUE, _FILTER_LABEL, "a word")
    ctx = _context(_criterion("filter"), refusals=REFUSALS_PER_CHECK)

    held = hold_an_option_to_its_parameter(
        ctx,
        FrameResult(disposition="needs_user", open_questions=[question, other]),
    )

    assert isinstance(held, FrameResult)
    assert held.open_questions == [
        question.model_copy(update={"options": []}),
        other,
    ]
    assert held.gaps == [
        PassGap(
            kind="option_not_a_value",
            sentence=(
                f"c_one.the_param offered a value the card cannot bind: "
                f"{_FILTER_LABEL!r} is not a value of the_param: it takes a filter "
                "value; 'a word' is not a value of the_param: it takes a filter "
                "value, so the question asks in free text."
            ),
        )
    ]
    assert ctx.deps.agent_state.refusals == REFUSALS_PER_CHECK


def _final(question: dict[str, object]) -> ToolCallPart:
    return ToolCallPart(
        tool_name="final_result",
        args=json.dumps({"disposition": "needs_user", "open_questions": [question]}),
    )


async def test_frame_retries_inside_its_own_run() -> None:
    told: list[str] = []
    asked = {
        "question": "Which value do you mean?",
        "dimension": "data_type",
        "recommended_value": "No filter",
        "criterion_id": "c_one",
        "param_name": "the_param",
    }

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = info.output_tools[0].name
        told.extend(
            str(part.content)
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, RetryPromptPart)
        )
        options = [] if told else [_FILTER_VALUE, _FILTER_LABEL]
        part = _final({**asked, "options": options})
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output, args=part.args, tool_call_id="call_final"
                )
            ]
        )

    ctx = _context(_criterion("filter"))
    agent = build_frame_agent()

    with agent.override(model=FunctionModel(_frame, model_name="scripted")):
        run = await agent.run("FRAME work order: frame it", deps=ctx.deps)

    assert isinstance(run.output, FrameResult)
    assert [q.options for q in run.output.open_questions] == [[]]
    assert run.output.gaps == []
    assert len(told) == 1
    assert f"{_FILTER_LABEL!r} is not a value of the_param" in told[0]
