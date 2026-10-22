"""FRAME's result checks run inside FRAME's run: the pass reads the correction
and answers again, and the caller receives only the answer it gave last."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb.domain.parameters import ParamValue, PhyleticExpression
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.services.strategies import reading_check
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_GPI = Constraint(
    kind=ConstraintKind.OTHER,
    label="predicted GPI anchor",
    requested_value="predicted GPI anchor",
    source=ConstraintSource.USER_EXPLICIT,
)


def _reports(number: str) -> dict[str, object]:
    return {
        "summary": "No search on this site states a predicted GPI anchor.",
        "disposition": "needs_research",
        "requirementProblems": [
            {"requirement": number, "problem": "site_has_no_search"}
        ],
    }


async def test_a_number_the_list_lacks_is_corrected_before_the_caller_reads_it() -> (
    None
):
    told: list[str] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        retries = [p for p in last.parts if isinstance(p, RetryPromptPart)]
        told.extend(str(p.content) for p in retries)
        number = "R1" if retries else "R4"
        return ModelResponse(parts=[ToolCallPart("final_result", _reports(number))])

    deps = agent_run_context().deps
    deps.agent_state.stated_requirements = [_GPI]
    agent = build_frame_agent()

    with agent.override(model=FunctionModel(_frame, model_name="scripted")):
        run = await agent.run("FRAME work order: frame it", deps=deps)

    assert isinstance(run.output, FrameResult)
    assert run.output.requirement_problems == [
        RequirementReport(
            requirement="R1", problem=RequirementProblem.SITE_HAS_NO_SEARCH
        )
    ]
    [sent_back] = told
    assert sent_back == (
        "requirement_problems names ['R4'], and the list holds R1. A report names "
        "a requirement by its number in 'Requirements the researcher stated'. Use "
        "one of those numbers, or leave the entry out and say it in summary."
    )


_HANDFUL = Constraint(
    kind=ConstraintKind.OTHER,
    label="restricted to a handful of microsporidia",
    requested_value="restricted to a handful of microsporidia",
    source=ConstraintSource.USER_EXPLICIT,
)
_FAMILIES = "c_microsporidia_families"
_EXPRESSION = "phyletic_expression"


def _readings(keys: list[str] | None) -> list[dict[str, str | list[str]]]:
    return [
        {
            "label": f"At most {n} Microsporidia genomes",
            "value": f"MICR>=1T AND MICR<={n}T",
            "caveat": f"Excludes families present in more than {n} genomes.",
        }
        | ({} if keys is None else {"requirements": keys})
        for n in (3, 5, 10)
    ]


def _asked(
    *,
    on_readings: list[str] | None,
    on_question: list[str],
    readings: int = 3,
    **question: object,
) -> dict[str, object]:
    return {
        "summary": "A handful needs a numeric upper bound.",
        "disposition": "needs_user",
        "openQuestions": [
            {
                "question": "How many Microsporidia genomes should a family occur in at most?",
                "dimension": "other",
                "recommendedValue": "At most 5 Microsporidia genomes",
                "readings": _readings(on_readings)[:readings],
                "criterionId": _FAMILIES,
                "paramName": _EXPRESSION,
                "requirements": on_question,
            }
            | question
        ],
        "requirementProblems": [
            {"requirement": "R2", "problem": "request_leaves_it_open"}
        ],
    }


@pytest.fixture
def echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


@pytest.fixture
def parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        PhyleticExpression.parse(parameters[_EXPRESSION].to_wire())
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


async def _run(
    answers: list[dict[str, object]],
    *,
    requirements: list[Constraint] | None = None,
    criterion_id: str = _FAMILIES,
) -> tuple[FrameResult, list[str]]:
    told: list[str] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        told.extend(
            str(p.content) for p in last.parts if isinstance(p, RetryPromptPart)
        )
        return ModelResponse(
            parts=[
                ToolCallPart("final_result", answers[min(len(told), len(answers) - 1)])
            ]
        )

    deps = agent_run_context(site_id="orthomcl").deps
    deps.agent_state.stated_requirements = (
        [_GPI, _HANDFUL] if requirements is None else requirements
    )
    deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=[
            Criterion(
                id=criterion_id,
                text="families restricted to a handful of microsporidia",
                search_name="GroupsByPhyleticPattern",
                record_class="group",
                open_params=[OpenSlot(param_name=_EXPRESSION, param_kind="string")],
            )
        ],
    )
    agent = build_frame_agent()
    with agent.override(model=FunctionModel(_frame, model_name="scripted")):
        run = await agent.run("FRAME work order: frame it", deps=deps)
    assert isinstance(run.output, FrameResult)
    return run.output, told


async def test_a_question_keyed_on_each_reading_reaches_the_caller_unretried(
    echoed: None,
) -> None:
    output, told = await _run([_asked(on_readings=["R2"], on_question=[])])

    assert told == []
    [question] = output.open_questions
    assert question.requirements == ["R2"]
    assert [r.value for r in question.readings] == [
        "MICR>=1T AND MICR<=3T",
        "MICR>=1T AND MICR<=5T",
        "MICR>=1T AND MICR<=10T",
    ]


async def test_a_question_keyed_nowhere_is_told_the_one_change(echoed: None) -> None:
    output, told = await _run(
        [
            _asked(on_readings=None, on_question=[]),
            _asked(on_readings=None, on_question=["R2"]),
        ]
    )

    assert told == [
        (
            "Change these readings, or ask nothing about them and say why in "
            f"summary: {_FAMILIES}.{_EXPRESSION}: name in the question's "
            "`requirements` the keys of the requirements its readings "
            "approximate, from R1, R2."
        )
    ]
    assert output.open_questions[0].requirements == ["R2"]


async def test_a_question_keyed_with_no_requirement_stated_reaches_the_caller(
    echoed: None,
) -> None:
    output, told = await _run(
        [
            _asked(on_readings=["R2"], on_question=[]),
            _asked(on_readings=None, on_question=[]),
            _asked(on_readings=["2"], on_question=[]),
        ],
        requirements=[],
    )

    assert [t.split(",")[0] for t in told] == [
        "requirement_problems names ['R2']",
        "requirement_problems names ['R2']",
    ]
    assert output.requirement_problems == []
    assert output.gaps == [
        PassGap(
            kind="report_dropped",
            sentence="The pass reported ['R2'], which the requirement list does not hold.",
        )
    ]
    [question] = output.open_questions
    assert [r.label for r in question.readings] == [
        "At most 3 Microsporidia genomes",
        "At most 5 Microsporidia genomes",
        "At most 10 Microsporidia genomes",
    ]


_BANDS = "c_copy_comparison"
_AGGREGATE = "All listed genomes, normalized per genome"
_SINGLE = "Representative single genomes"
_SCOPE = (
    "Which genome scope should define more genes per genome: aggregate all "
    "listed genomes, or compare specified representative genomes?"
)


def _bands(keys: list[str]) -> dict[str, object]:
    return {
        "disposition": "needs_user",
        "summary": "One open expression slot.",
        "openQuestions": [
            {
                "question": _SCOPE,
                "dimension": "comparator",
                "recommendedValue": _AGGREGATE,
                "criterionId": _BANDS,
                "paramName": _EXPRESSION,
                "readings": [
                    {
                        "label": _AGGREGATE,
                        "value": (
                            "Toxoplasma total versus Plasmodium total, normalized "
                            "by 15 and 61 genomes using copy-count bands"
                        ),
                        "requirements": keys,
                    },
                    {
                        "label": _SINGLE,
                        "value": (
                            "A specified Toxoplasma genome has more proteins than "
                            "a specified Plasmodium genome"
                        ),
                        "requirements": keys,
                    },
                ],
            }
        ],
        "requirementProblems": [],
    }


def _stated(*values: str) -> list[Constraint]:
    return [
        Constraint(
            kind=ConstraintKind.OTHER,
            label=value,
            requested_value=value,
            source=ConstraintSource.USER_EXPLICIT,
        )
        for value in values
    ]


async def test_prose_readings_are_dropped_with_the_site_s_reasons(
    parsed: None,
) -> None:
    output, told = await _run(
        [_bands(["R1", "R2", "R4"]), _bands(["1", "2", "4"]), _bands(["R4"])],
        requirements=_stated(
            "ortholog groups",
            "Toxoplasma",
            "Plasmodium",
            "more genes per genome",
        ),
        criterion_id=_BANDS,
    )

    assert len(told) == REFUSALS_PER_CHECK
    assert all(t.startswith("Change these readings") for t in told)
    [question] = output.open_questions
    assert (question.question, question.readings, question.requirements) == (
        _SCOPE,
        [],
        ["R4"],
    )
    [gap] = output.gaps
    assert gap.kind == "question_without_readings"
    assert gap.sentence == (
        f"{_SCOPE!r} reaches the card with no readings: the site refuses "
        f"{_AGGREGATE!r} on {_BANDS}.{_EXPRESSION}: phyletic_expression is not a "
        "phyletic pattern expression: In 'Toxoplasma total versus Plasmodium "
        "total, normalized by 15 and 61 genomes using copy-count bands', "
        "'Toxoplasma' needs an operator and a count; the site refuses "
        f"{_SINGLE!r} on {_BANDS}.{_EXPRESSION}: phyletic_expression is not a "
        "phyletic pattern expression: In 'A specified Toxoplasma genome has more "
        "proteins than a specified Plasmodium genome', 'A' needs an operator and "
        "a count."
    )


def _one_reading() -> dict[str, object]:
    return _asked(on_readings=None, on_question=[], readings=1)


def _beside_options() -> dict[str, object]:
    return _asked(on_readings=["R2"], on_question=[], options=["3", "5"])


async def test_two_unkeyed_answers_then_one_reading_ends_without_a_retry_error(
    echoed: None,
) -> None:
    output, told = await _run(
        [
            _asked(on_readings=None, on_question=[]),
            _asked(on_readings=None, on_question=[]),
            _one_reading(),
        ]
    )

    assert len(told) == REFUSALS_PER_CHECK
    [question] = output.open_questions
    assert question.readings == []
    assert [g.kind for g in output.gaps] == ["question_without_readings"]


async def test_options_beside_readings_repeated_ends_without_a_retry_error(
    echoed: None,
) -> None:
    output, told = await _run([_beside_options()])

    assert [t.split(":")[1].strip() for t in told] == [
        f"{_FAMILIES}.{_EXPRESSION} offers the readings ['At most 3 Microsporidia genomes', 'At most 5 Microsporidia genomes', 'At most 10 Microsporidia genomes']",
    ] * REFUSALS_PER_CHECK
    [question] = output.open_questions
    assert (question.options, question.readings) == (["3", "5"], [])
    assert output.gaps[0].kind == "question_without_readings"


def _undecided() -> dict[str, object]:
    return _asked(on_readings=["R2"], on_question=[], recommendedValue="")


async def test_every_check_shares_one_bound_and_the_last_answer_passes(
    echoed: None,
) -> None:
    output, told = await _run(
        [_undecided(), _asked(on_readings=None, on_question=[]), _undecided()]
    )

    assert [t.split(" ")[0] for t in told] == ["These", "Change"]
    assert [g.kind for g in output.gaps] == ["question_decides_nothing"]


async def test_readings_left_unkeyed_past_the_bound_say_a_pick_replaces_none(
    echoed: None,
) -> None:
    output, told = await _run([_asked(on_readings=None, on_question=[])])

    assert len(told) == REFUSALS_PER_CHECK
    assert output.gaps == [
        PassGap(
            kind="readings_name_no_requirement",
            sentence=(
                "'How many Microsporidia genomes should a family occur in at most?' "
                "names no stated requirement, so a pick of its readings replaces none."
            ),
        )
    ]
    [question] = output.questions(requirements=[_GPI, _HANDFUL])
    assert [
        (read.replaces, read.names_no_requirement)
        for o in question.options
        if (read := o.offered_reading()) is not None
    ] == [([], True)] * 3
