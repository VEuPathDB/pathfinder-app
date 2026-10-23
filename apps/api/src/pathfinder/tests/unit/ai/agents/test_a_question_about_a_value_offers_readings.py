from __future__ import annotations

from collections.abc import Mapping

import pytest
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
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.frame_choice_checks import hold_a_choice_to_its_readings
from pathfinder.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.services.strategies import reading_check
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "phyletic_expression"
_PANEL = "c_panel"
_ALL, _MOST = "AAAA=10T", "AAAA>=9T"
_PICK = "c_pick"
_ORGANISM = "organism"
_STATED = [
    Constraint(
        kind=ConstraintKind.OTHER,
        label=label,
        requested_value=label,
        source=ConstraintSource.USER_EXPLICIT,
    )
    for label in ("the panel of genomes", "a missing marker")
]


def _slot(cid: str, param: str, **fields: object) -> OpenSlot:
    return OpenSlot.model_validate(
        {"criterionId": cid, "paramName": param, "question": "?"} | fields
    )


def _panel(**fields: object) -> Criterion:
    return Criterion.model_validate(
        {
            "id": _PANEL,
            "text": "present in the panel's genomes",
            "searchName": "GroupsByPhyleticPattern",
            "recordClass": "group",
            "openParams": [_slot(_PANEL, _EXPRESSION, paramKind="string")],
        }
        | fields
    )


def _picked(*slots: OpenSlot) -> Criterion:
    return Criterion(
        id=_PICK,
        text="records picked",
        search_name="AnySearch",
        open_params=list(slots),
    )


def _context(*criteria: Criterion, refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    state = ctx.deps.agent_state
    state.operational_spec_draft = OperationalSpec(criteria=list(criteria))
    state.stated_requirements = list(_STATED)
    state.refusals = refusals
    return ctx


def _question(**fields: object) -> SlotQuestion:
    return SlotQuestion.model_validate(
        {
            "question": "Which genomes should the panel hold?",
            "dimension": ConstraintKind.ORGANISM,
            "recommendedValue": "every genome",
            "criterionId": _PANEL,
            "paramName": _EXPRESSION,
        }
        | fields
    )


def _readings() -> list[Reading]:
    return [
        Reading(label="Every genome", value=_ALL),
        Reading(label="All but one genome", value=_MOST),
    ]


def _asked(
    *questions: SlotQuestion, reports: list[RequirementReport] | None = None
) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=list(questions),
        requirement_problems=list(reports or []),
    )


def _report(key: str, problem: RequirementProblem) -> RequirementReport:
    return RequirementReport(requirement=key, problem=problem)


_OPEN = RequirementProblem.REQUEST_LEAVES_IT_OPEN


def test_a_free_text_question_on_an_expression_slot_is_sent_back() -> None:
    ctx = _context(_panel())

    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(ctx, _asked(_question()))

    said = str(sent_back.value)
    assert f"{_PANEL}.{_EXPRESSION} in words" in said
    assert "two or three `readings`" in said
    assert ctx.deps.agent_state.refusals == 1


def test_at_the_bound_the_question_reaches_the_card_with_a_named_gap() -> None:
    question = _question()

    held = hold_a_choice_to_its_readings(
        _context(_panel(), refusals=REFUSALS_PER_CHECK), _asked(question)
    )

    assert isinstance(held, FrameResult)
    assert held.open_questions == [question]
    assert held.gaps == [
        PassGap(
            kind="question_without_readings",
            sentence=(
                f"{question.question!r} asks for {_PANEL}.{_EXPRESSION} in words, "
                "with no reading the site builds."
            ),
        )
    ]


def test_a_question_with_readings_and_their_counts_reaches_the_card() -> None:
    counted = _panel(
        measurements=[
            Measurement(kind="reading", param=_EXPRESSION, reading=_ALL, count=212),
            Measurement(kind="reading", param=_EXPRESSION, reading=_MOST, count=1874),
        ]
    )
    asked = _asked(_question(readings=_readings(), requirements=["R1"]))

    assert hold_a_choice_to_its_readings(_context(counted), asked) == asked
    spec = OperationalSpec.model_validate(
        {"recordType": "group", "criteria": [counted]}
    )
    assert [o.label for q in asked.questions(spec) for o in q.options] == [
        "Every genome: 212 groups",
        "All but one genome: 1874 groups",
    ]


def test_free_text_values_offered_as_options_are_sent_back_for_readings() -> None:
    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(
            _context(_panel()), _asked(_question(options=[_ALL, _MOST]))
        )

    assert "two or three `readings`" in str(sent_back.value)


def test_a_bound_expression_asked_again_in_words_is_sent_back() -> None:
    bound = _panel(
        openParams=[],
        resolvedParams={
            _EXPRESSION: BoundValue(value=StringValue(value=_ALL), source="chosen")
        },
    )

    with pytest.raises(ModelRetry):
        hold_a_choice_to_its_readings(_context(bound), _asked(_question()))


def test_a_question_about_no_value_stays_in_words() -> None:
    asked = _asked(
        SlotQuestion(
            question="Which organism do you work on?",
            dimension=ConstraintKind.ORGANISM,
            recommended_value="the one the researcher names",
        )
    )

    assert hold_a_choice_to_its_readings(_context(), asked) == asked


def test_candidates_on_no_slot_are_sent_back_to_name_the_slot_they_set() -> None:
    asked = _asked(
        _question(criterionId="", paramName="", options=["Group A", "Group B", "C"])
    )

    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(_context(_panel()), asked)

    assert "names no `criterion_id` and `param_name`" in str(sent_back.value)


def test_a_yes_or_no_on_no_slot_passes() -> None:
    asked = _asked(_question(criterionId="", paramName="", options=["Yes", "No"]))

    assert hold_a_choice_to_its_readings(_context(), asked) == asked


_H11_STATED = [
    Constraint(
        kind=ConstraintKind.ORGANISM,
        label="trypanosomatid organisms",
        requested_value="trypanosomatid",
        source=ConstraintSource.USER_EXPLICIT,
    ),
    Constraint(
        kind=ConstraintKind.OTHER,
        label="absence of a human counterpart",
        requested_value="gene families with no human counterpart",
        source=ConstraintSource.USER_EXPLICIT,
    ),
]
_H11_FRAME = {
    "disposition": "needs_user",
    "summary": "No clade code names the group.",
    "openQuestions": [
        {
            "question": (
                "Which trypanosomatid genomes or species should define the family "
                "set? The search can then require presence in that selected list "
                "and absence from human."
            ),
            "dimension": "organism",
            "recommendedValue": "Specify the trypanosomatid species/genomes to include",
            "options": [
                "Trypanosoma brucei",
                "Trypanosoma cruzi",
                "Trypanosoma vivax",
                "Leishmania species",
                "A custom list of trypanosomatid genomes",
            ],
        }
    ],
    "requirementProblems": [{"requirement": "R1", "problem": "site_has_no_search"}],
}


def test_candidates_about_a_requirement_no_search_states_are_sent_back() -> None:
    ctx = _context()
    ctx.deps.agent_state.stated_requirements = list(_H11_STATED)

    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(ctx, FrameResult.model_validate(_H11_FRAME))

    assert "names no `criterion_id` and `param_name`" in str(sent_back.value)


def test_a_value_left_open_with_no_question_is_sent_back() -> None:
    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(
            _context(_panel()), _asked(reports=[_report("R2", _OPEN)])
        )

    assert "R2 is reported request_leaves_it_open" in str(sent_back.value)


def test_a_value_left_open_degrades_to_a_named_gap_at_the_bound() -> None:
    held = hold_a_choice_to_its_readings(
        _context(_panel(), refusals=REFUSALS_PER_CHECK),
        _asked(reports=[_report("R2", _OPEN)]),
    )

    assert isinstance(held, FrameResult)
    assert held.gaps == [
        PassGap(
            kind="question_without_readings",
            sentence="The pass leaves R2 open and asks no question for it.",
        )
    ]


def test_a_value_left_open_and_asked_with_readings_reaches_the_card() -> None:
    asked = _asked(
        _question(readings=_readings(), requirements=["R2"]),
        reports=[_report("R2", _OPEN)],
    )

    assert hold_a_choice_to_its_readings(_context(_panel()), asked) == asked


def test_one_keyless_question_leaves_a_second_open_value_sent_back() -> None:
    asked = _asked(
        _question(readings=_readings()),
        reports=[_report("R1", _OPEN), _report("R2", _OPEN)],
    )

    with pytest.raises(ModelRetry) as sent_back:
        hold_a_choice_to_its_readings(_context(_panel()), asked)

    said = str(sent_back.value)
    assert "R2 is reported request_leaves_it_open" in said
    assert "R1 is reported" not in said


@pytest.fixture
def echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


async def _chain(criterion: Criterion, asked: FrameResult) -> FrameResult:
    ctx = _context(criterion)
    held = hold_a_choice_to_its_readings(ctx, asked)
    assert isinstance(held, FrameResult)
    read = await hold_the_readings_to_the_site(ctx, held)
    assert isinstance(read, FrameResult)
    return read


def _pick_question(param: str, **fields: object) -> SlotQuestion:
    return _question(criterionId=_PICK, paramName=param, **fields)


@pytest.mark.parametrize(
    ("slot", "param"),
    [
        (_slot(_PICK, "ds_gene_ids", paramKind="input-dataset"), "ds_gene_ids"),
        (
            _slot(_PICK, "query_sequence", paramKind="string", pasted=True),
            "query_sequence",
        ),
    ],
)
async def test_a_value_only_the_researcher_holds_is_asked_in_words(
    echoed: None, slot: OpenSlot, param: str
) -> None:
    asked = _asked(
        _pick_question(param, requirements=["R1"]), reports=[_report("R1", _OPEN)]
    )

    assert await _chain(_picked(slot), asked) == asked


async def test_a_vocabulary_value_left_open_is_asked_with_its_values(
    echoed: None,
) -> None:
    organisms = _slot(
        _PICK,
        _ORGANISM,
        paramKind="multi-pick-vocabulary",
        options=[f"Organism {n}" for n in range(30)],
    )
    asked = _asked(
        _pick_question(
            _ORGANISM, options=["Organism 1", "Organism 2"], requirements=["R1"]
        ),
        reports=[_report("R1", _OPEN)],
    )

    assert await _chain(_picked(organisms), asked) == asked


async def test_a_text_slot_with_a_listed_vocabulary_is_asked_with_its_values(
    echoed: None,
) -> None:
    listed = _slot(_PICK, "saved_strategy", paramKind="string", options=["One", "Two"])
    asked = _asked(_pick_question("saved_strategy", options=["One", "Two"]))

    assert await _chain(_picked(listed), asked) == asked


async def test_a_text_slot_beside_another_open_slot_is_asked_in_words(
    echoed: None,
) -> None:
    criterion = _picked(
        _slot(_PICK, "text_expression", paramKind="string"),
        _slot(
            _PICK, "text_fields", paramKind="multi-pick-vocabulary", options=["a", "b"]
        ),
    )
    asked = _asked(_pick_question("text_expression"))

    assert await _chain(criterion, asked) == asked


async def test_frame_sends_a_free_text_expression_question_back_in_its_run(
    echoed: None,
) -> None:
    told: list[str] = []
    answers = [
        {"disposition": "needs_user", "summary": "s", "openQuestions": [q]}
        for q in (
            _question(requirements=["R1"]).model_dump(by_alias=True),
            _question(readings=_readings(), requirements=["R1"]).model_dump(
                by_alias=True
            ),
        )
    ]

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        told.extend(
            str(p.content) for p in last.parts if isinstance(p, RetryPromptPart)
        )
        answer = answers[min(len(told), len(answers) - 1)]
        return ModelResponse(parts=[ToolCallPart("final_result", answer)])

    deps = _context(_panel()).deps
    agent = build_frame_agent()
    with agent.override(model=FunctionModel(_frame, model_name="scripted")):
        run = await agent.run("FRAME work order: frame it", deps=deps)

    assert [t.split(":")[0] for t in told] == [
        "A question about a value the site builds offers what the site builds"
    ]
    assert isinstance(run.output, FrameResult)
    assert [r.value for r in run.output.open_questions[0].readings] == [_ALL, _MOST]
