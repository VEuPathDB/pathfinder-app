"""A reading the researcher accepts binds its value, stands in for the
requirement its question names, and reaches the check with its caveat."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb_mcp.catalog import ParameterInfo, ValidatedParams

from strategist.ai.agents.verification import (
    pinned_researcher_request,
)
from strategist.ai.graph.runtime import AgentDeps, VerificationScope
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.graph.turn_records import AnsweredQuestions
from strategist.ai.lead import frame_dispatch, lead_consult
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.ai.lead.frame_dispatch import run_frame
from strategist.ai.lead.lead_consult import consult_user
from strategist.ai.lead.ledger_render import render_frame_full
from strategist.ai.lead.ledger_sections import FrameSection
from strategist.ai.lead.recorded_cards import card_questions
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.caveats import caveats_for
from strategist.domain.reading_caveats import ReadingCaveat
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from strategist.domain.strategy.questions import OpenQuestion, SlotQuestion
from strategist.domain.strategy.readings import (
    AcceptedReading,
    Reading,
    ReadingChooser,
)
from strategist.services.strategies import reading_check
from strategist.tests._support.requirement_values import without_ids
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)
from strategist.tests.unit.ai.tools.conftest import agent_run_context

EVERY, SHARE = "PLAS=61T AND TOXO=0T", "PLAS>=55T AND TOXO=0T"
_EXPRESSION = "phyletic_expression"
_SEARCH = "GroupsByPhyleticPattern"
_PROMPT = "Present in which Plasmodium genomes?"
_EVERY_LABEL = "Every one of the 61 genomes"
_SHARE_LABEL = "At least 55 of the 61 genomes (90%)"
_SHARE_CAVEAT = "Keeps groups missing from up to 6 genomes"
_PRESENT = requirement(
    ConstraintKind.UNTYPED, "presence", "present in all Plasmodium species"
)
_STAGE = requirement(ConstraintKind.UNTYPED, "stage", "expressed in blood stages")
_STAND_IN = Constraint(
    kind=ConstraintKind.UNTYPED,
    requested_value=_SHARE_LABEL,
    label=_PROMPT,
    source=ConstraintSource.USER_EXPLICIT,
    hard=True,
)
_LINE = f"'{_SHARE_LABEL}', stated by Expression = {SHARE}; its caveat: {_SHARE_CAVEAT}"


@pytest.fixture(autouse=True)
def _published_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    sheet = [
        ParameterInfo.model_validate(
            {
                "name": _EXPRESSION,
                "display_name": "Expression",
                "type": "string",
                "required": True,
                "is_visible": True,
                "help": "",
                "value_format": "",
            }
        )
    ]

    async def _sheets(
        *, site_id: str, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id
        return {name: sheet for name in search_names if name == _SEARCH}

    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)
    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


def _plasmodium(
    measurements: list[Measurement] | None = None, value: str = EVERY
) -> Criterion:
    return Criterion(
        id="c_plas",
        text="groups in every Plasmodium genome and in no Toxoplasma genome",
        search_name=_SEARCH,
        record_class="group",
        resolved_params={
            _EXPRESSION: BoundValue(value=StringValue(value=value), source="chosen")
        },
        param_display_names={_EXPRESSION: "Expression"},
        measurements=measurements
        if measurements is not None
        else [
            Measurement(kind="reading", param=_EXPRESSION, reading=SHARE, count=1088)
        ],
        result_count=395,
    )


def _spec(criterion: Criterion | None = None) -> OperationalSpec:
    return OperationalSpec(
        goal="groups present in all Plasmodium species, absent from Toxoplasma",
        criteria=[criterion or _plasmodium()],
    )


def _slot_question() -> SlotQuestion:
    return SlotQuestion(
        question=_PROMPT,
        recommended_value=_EVERY_LABEL,
        criterion_id="c_plas",
        param_name=_EXPRESSION,
        requirements=["R1"],
        readings=[
            Reading(label=_EVERY_LABEL, value=EVERY),
            Reading(label=_SHARE_LABEL, value=SHARE, caveat=_SHARE_CAVEAT),
        ],
    )


def _question() -> OpenQuestion:
    return _slot_question().typed(_plasmodium(), noun="group", replaces=[_PRESENT.id])


def _deps(spec: OperationalSpec, *questions: OpenQuestion) -> LeadDeps:
    return lead_deps(
        pipeline_state(
            "orthomcl",
            user_prompt=(
                "Which groups are present in all Plasmodium species, expressed "
                "in blood stages, and absent from Toxoplasma?"
            ),
            domain=StrategyDomainState(
                operational_spec=spec,
                open_questions=list(questions),
                requirements=[_PRESENT, _STAGE],
            ),
        )
    )


async def _picked(label: str) -> LeadDeps:
    question = _question()
    deps = _deps(_spec(), question)
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(question_id="q1", prompt=_PROMPT, chosen_labels=[label])
        ]
    }
    await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([question]),
        reply="Two readings of every species.",
    )
    return deps


def _held(stand_in: str = "") -> AcceptedReading:
    return AcceptedReading(
        reading=_SHARE_LABEL,
        caveat=_SHARE_CAVEAT,
        params={_EXPRESSION: SHARE},
        replaces=[_PRESENT.id],
        stand_in=stand_in,
        chosen_by=ReadingChooser.RESEARCHER_ON_A_CARD,
    )


def _stand_in(deps: LeadDeps, value: str = _SHARE_LABEL) -> str:
    domain = deps.state.domain
    recorded = [
        *domain.requirements,
        *(r.constraint for r in domain.retired_requirements),
    ]
    [held] = [c.id for c in recorded if c.requested_value == value]
    return held


def _criterion(deps: LeadDeps) -> Criterion:
    spec = deps.state.domain.operational_spec
    assert spec is not None
    [criterion] = spec.criteria
    return criterion


async def test_a_picked_reading_binds_its_value_as_the_cards() -> None:
    deps = await _picked(f"{_SHARE_LABEL}: 1088 groups")

    criterion = _criterion(deps)
    assert criterion.resolved_params[_EXPRESSION].value == StringValue(value=SHARE)
    assert criterion.resolved_params[_EXPRESSION].source == "card"
    assert criterion.held_reading == _held(_stand_in(deps))


async def test_a_picked_reading_stands_in_for_the_requirement_its_question_names() -> (
    None
):
    deps = await _picked(f"{_SHARE_LABEL}: 1088 groups")

    domain = deps.state.domain
    assert without_ids(domain.requirements) == without_ids([_STAGE, _STAND_IN])
    assert [(r.constraint, r.lifecycle) for r in domain.retired_requirements] == [
        (_PRESENT, ReplacedLifecycle(by=_stand_in(deps)))
    ]


async def test_the_caveat_of_a_picked_reading_reaches_the_facts() -> None:
    deps = await _picked(f"{_SHARE_LABEL}: 1088 groups")

    assert caveats_for(deps.state.domain.operational_spec, []) == [
        ReadingCaveat(criterion_id="c_plas", reading=_SHARE_LABEL, caveat=_SHARE_CAVEAT)
    ]


async def test_a_picked_reading_without_a_caveat_adds_no_caveat() -> None:
    deps = await _picked(f"{_EVERY_LABEL}: 395 groups")

    criterion = _criterion(deps)
    assert criterion.held_reading == AcceptedReading(
        reading=_EVERY_LABEL,
        params={_EXPRESSION: EVERY},
        replaces=[_PRESENT.id],
        stand_in=_stand_in(deps, _EVERY_LABEL),
        chosen_by=ReadingChooser.RESEARCHER_ON_A_CARD,
    )
    assert caveats_for(deps.state.domain.operational_spec, []) == []


def _ask(deps: LeadDeps, label: str) -> None:
    question = deps.state.domain.open_questions[0]
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card_2", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card_2": [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=[label]
            )
        ]
    }


async def test_a_card_that_rebinds_the_value_ends_the_reading_and_its_stand_in() -> (
    None
):
    deps = await _picked(f"{_SHARE_LABEL}: 1088 groups")
    first = _stand_in(deps)
    question = _question()
    deps.state.domain.open_questions = [question]
    _ask(deps, f"{_EVERY_LABEL}: 395 groups")

    await consult_user(
        run_context_for(deps, "call_card_2"),
        questions=card_questions([question]),
        reply="Again.",
    )

    retired = {
        r.constraint.id: r.lifecycle for r in deps.state.domain.retired_requirements
    }
    assert retired[first] == WithdrawnLifecycle(turn_id="")
    assert [c.requested_value for c in deps.state.domain.requirements] == [
        _STAGE.requested_value,
        _EVERY_LABEL,
    ]


def _stub_stream(
    monkeypatch: pytest.MonkeyPatch, result: FrameResult, bind: str
) -> None:
    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        draft = agent_deps.agent_state.operational_spec_draft
        draft.criteria = [
            _plasmodium(measurements=[], value=bind).model_copy(
                update={"accepted_reading": None if bind == EVERY else _held()}
            )
        ]
        return result

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


async def test_a_reading_frame_bound_from_an_answer_in_words_stands_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(_spec())
    deps.state.turn_markers.answered = AnsweredQuestions(
        questions=[_question()], answer="most of them is enough"
    )
    _stub_stream(monkeypatch, FrameResult(disposition="spec_ready"), SHARE)

    await run_frame(deps=deps, parent_tool_call_id="call_frame", work_order="frame")

    assert without_ids(deps.state.domain.requirements) == without_ids(
        [_STAGE, _STAND_IN]
    )
    assert _criterion(deps).held_reading == _held(_stand_in(deps))


async def test_each_offered_reading_is_counted_into_its_label_when_it_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(_spec(_plasmodium(measurements=[])))
    counts = {EVERY: 395, SHARE: None}

    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
        *,
        timeout_seconds: float,
    ) -> int | None:
        del site_id, record_type, search_name, timeout_seconds
        return counts[params[_EXPRESSION].to_wire()]

    monkeypatch.setattr(deps.turn_counts, "count", _count)
    result = FrameResult(disposition="needs_user", open_questions=[_slot_question()])
    _stub_stream(monkeypatch, result, EVERY)

    framed = await run_frame(
        deps=deps, parent_tool_call_id="call_frame", work_order="frame"
    )

    assert isinstance(framed, FrameResult)
    assert [o.label for q in framed.card_questions for o in q.options] == [
        f"{_EVERY_LABEL}: 395 groups",
        _SHARE_LABEL,
    ]
    assert _criterion(deps).measurements == [
        Measurement(kind="reading", param=_EXPRESSION, reading=EVERY, count=395)
    ]


_ASKED = "Which groups are present in all Plasmodium species?"
_REQUEST = ["## The researcher's request", f"1. {_ASKED}"]


def test_verify_reads_the_request_numbered() -> None:
    ctx = agent_run_context()
    ctx.deps.verification_scope = VerificationScope(messages=[_ASKED])

    assert pinned_researcher_request(ctx) == "\n".join(_REQUEST)


def test_the_ledger_shows_a_held_reading_under_its_criterion() -> None:
    spec = _spec(
        _plasmodium(value=SHARE).model_copy(update={"accepted_reading": _held()})
    )

    rendered = render_frame_full(FrameSection(spec=spec)).splitlines()

    assert [line for line in rendered if "READING" in line] == [
        f"    READING picked by the researcher on a card: {_LINE}"
    ]


def _offered(deps: LeadDeps) -> list[str]:
    return [
        r.reading
        for r in agent_deps_for(deps, call_id="call_test").agent_state.offered_readings
    ]


def test_a_pass_is_offered_the_readings_of_an_open_question() -> None:
    assert _offered(_deps(_spec(), _question())) == [_EVERY_LABEL, _SHARE_LABEL]


def test_a_pass_is_offered_the_readings_of_a_question_this_message_answered() -> None:
    deps = _deps(_spec())
    deps.state.turn_markers.answered = AnsweredQuestions(
        questions=[_question()], answer="most of them is enough"
    )

    assert _offered(deps) == [_EVERY_LABEL, _SHARE_LABEL]


def test_a_pass_is_offered_no_reading_of_a_question_an_earlier_message_answered() -> (
    None
):
    deps = _deps(_spec())
    deps.state.domain.answered_questions = [_question()]

    assert _offered(deps) == []
