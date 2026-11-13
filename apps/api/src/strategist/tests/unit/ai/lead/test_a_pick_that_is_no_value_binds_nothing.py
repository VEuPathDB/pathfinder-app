from __future__ import annotations

from collections.abc import Collection

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic import TypeAdapter
from pydantic_ai.messages import ToolReturn, ToolReturnPart
from veupathdb.domain.parameters import ParamKind, from_wire
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import lead_consult
from strategist.ai.lead.lead_consult import CardAnswer, consult_user
from strategist.ai.lead.recorded_cards import card_questions
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues, TypedOption
from strategist.domain.strategy.questions import OpenQuestion
from strategist.domain.strategy.readings import ReadValues
from strategist.tests._support.recorded_searches import client_search
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByGeneModelChars"
_FILTER = "gene_model_char"
_LABEL = "Low nucleotide diversity per CDS site"
_NO_FILTER = '{"filters": []}'
_FILTER_VALUE = '{"filters": [{"field": "sex", "value": ["female"]}]}'
_PROMPT = "Which genes do you mean?"
_BINDS_NOTHING = (
    f"{_LABEL!r} binds nothing: {_LABEL!r} is not a value of {_FILTER}: it takes a "
    "filter value. Run frame_problem again so it offers values this parameter "
    "takes, or asks in free text"
)


@pytest.fixture(autouse=True)
def _published_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    sheet = format_param_info_typed(
        client_search("search_genes_by_gene_model_chars").parameters or []
    )

    async def _sheets(
        *, site_id: str, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id
        return dict.fromkeys(search_names, sheet)

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)


def _criterion(**fields: object) -> Criterion:
    return Criterion.model_validate(
        {"id": "c_one", "text": "one property", "searchName": _SEARCH} | fields
    )


def _open_on(kind: ParamKind, name: str = _FILTER) -> Criterion:
    return _criterion(
        openParams=[OpenSlot(criterion_id="c_one", param_name=name, param_kind=kind)]
    )


def _option(label: str, value: str, name: str = _FILTER) -> TypedOption:
    return TypedOption(
        id=label.lower().replace(" ", "-"),
        label=label,
        binding=SetValues(criterion_id="c_one", params={name: value}),
    )


def _stored(*options: TypedOption) -> OpenQuestion:
    return OpenQuestion(
        question=_PROMPT,
        dimension=ConstraintKind.UNTYPED,
        recommended_value=_LABEL,
        criterion_id="c_one",
        options=list(options),
    )


async def _clicked(
    criterion: Criterion, question: OpenQuestion, label: str
) -> tuple[LeadDeps, ToolReturn[list[UserQuestionAnswer]]]:
    deps = lead_deps(
        pipeline_state(
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(criteria=[criterion]),
                open_questions=[question],
            ),
        )
    )
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(question_id="q1", prompt=_PROMPT, chosen_labels=[label])
        ]
    }
    returned = await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([question]),
        reply="One value decides it.",
    )
    return deps, returned


def _told(returned: ToolReturn[list[UserQuestionAnswer]]) -> list[str]:
    part = ToolReturnPart(
        tool_name="consult_user", content=returned.return_value, tool_call_id="c"
    )
    answers = TypeAdapter(list[CardAnswer]).validate_json(part.model_response_str())
    return [why for answer in answers for why in answer.refused]


def _bound_on(deps: LeadDeps) -> Criterion:
    spec = deps.state.domain.operational_spec
    assert spec is not None
    return spec.criteria[0]


def _answer_told(deps: LeadDeps) -> str:
    answered = deps.state.turn_markers.answered
    assert answered is not None
    return answered.answer


async def test_a_stored_label_on_a_filter_becomes_a_refusal() -> None:
    criterion = _open_on("filter")
    question = _stored(_option(_LABEL, _LABEL), _option("No filter", _NO_FILTER))

    deps, returned = await _clicked(criterion, question, _LABEL)

    assert _bound_on(deps) == criterion
    assert _BINDS_NOTHING in _answer_told(deps)
    assert _told(returned) == [_BINDS_NOTHING]
    assert deps.state.domain.open_questions == []
    assert deps.state.domain.requirements == []


async def test_the_sheet_alone_can_name_the_kind() -> None:
    criterion = _criterion()
    question = _stored(_option(_LABEL, _LABEL), _option("No filter", _NO_FILTER))

    deps, returned = await _clicked(criterion, question, _LABEL)

    assert _bound_on(deps) == criterion
    assert _told(returned) == [_BINDS_NOTHING]


async def test_a_stored_label_on_a_held_filter_keeps_the_held_value() -> None:
    held = BoundValue(value=from_wire("filter", _NO_FILTER), source="default")
    criterion = _criterion(resolvedParams={_FILTER: held})
    question = _stored(_option(_LABEL, _LABEL), _option("No filter", _NO_FILTER))

    deps, _ = await _clicked(criterion, question, _LABEL)

    assert _bound_on(deps).resolved_params[_FILTER].value == held.value


async def test_a_stored_label_on_a_number_becomes_a_refusal() -> None:
    criterion = _open_on("number", "a_number")
    question = _stored(
        _option(_LABEL, _LABEL, "a_number"), _option("Eighty", "80", "a_number")
    )

    deps, returned = await _clicked(criterion, question, _LABEL)

    assert _bound_on(deps) == criterion
    assert "it takes a number value" in _told(returned)[0]


async def test_a_stored_label_on_an_expression_becomes_a_refusal() -> None:
    name = "phyletic_expression"
    label = "Keep the 2-5 Plasmodium-copy criterion only"
    criterion = _open_on("string", name)
    question = _stored(
        _option(label, label, name), _option("Absent", "APIC>=1T AND MAMM=0T", name)
    )

    deps, returned = await _clicked(criterion, question, label)

    assert _bound_on(deps) == criterion
    assert f"{label!r} is not a value of {name}" in _told(returned)[0]


async def test_a_stored_reading_with_a_label_becomes_a_refusal() -> None:
    criterion = _open_on("filter").model_copy(update={"record_class": "transcript"})
    reading = TypedOption(
        id="a-reading",
        label=_LABEL,
        binding=ReadValues(
            criterion_id="c_one", params={_FILTER: _LABEL}, reading=_LABEL
        ),
    )
    question = _stored(reading, _option("No filter", _NO_FILTER))

    deps, returned = await _clicked(criterion, question, _LABEL)

    assert _bound_on(deps).accepted_reading is None
    assert _told(returned) == [_BINDS_NOTHING]


async def test_a_thread_with_no_spec_binds_nothing_and_refuses_nothing() -> None:
    question = _stored(_option(_LABEL, _LABEL), _option("No filter", _NO_FILTER))
    deps = lead_deps(
        pipeline_state(domain=StrategyDomainState(open_questions=[question]))
    )
    answers = [
        UserQuestionAnswer(question_id="q1", prompt=_PROMPT, chosen_labels=[_LABEL])
    ]
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {"call_card": answers}

    returned = await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([question]),
        reply="One value decides it.",
    )

    assert (_told(returned), deps.state.domain.operational_spec) == ([], None)


async def test_a_value_the_parameter_takes_binds_and_tells_nothing_more() -> None:
    criterion = _open_on("filter")
    question = _stored(_option("Female", _FILTER_VALUE), _option("No", _NO_FILTER))

    deps, returned = await _clicked(criterion, question, "Female")

    assert (
        _bound_on(deps).resolved_params[_FILTER].value.to_decoded()
        == from_wire("filter", _FILTER_VALUE).to_decoded()
    )
    assert _told(returned) == []
    assert "binds nothing" not in _answer_told(deps)
