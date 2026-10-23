"""A reading reaches the card only when the site validates its value on a
parameter no vocabulary offers, and a pick the site refuses binds nothing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Collection, Mapping

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import ParamKind, ParamValue, StringValue
from veupathdb.errors import ValidationError, WDKError
from veupathdb_mcp.catalog import ParameterInfo, ValidatedParams

from pathfinder.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_consult
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.recorded_cards import card_questions
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
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
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

EVERY, SHARE = "PLAS=61T AND TOXO=0T", "PLAS>=55T AND TOXO=0T"
_SPACED = "PLAS>=55T  AND  TOXO=0T"
_EXPRESSION = "phyletic_expression"
_SEARCH = "GroupsByPhyleticPattern"
_SHARE_LABEL = "At least 55 of the 61 genomes (90%)"
_REFUSAL = "The expression names the code PLAS, which the taxonomy does not carry"
_PRESENT = Constraint(
    kind=ConstraintKind.OTHER,
    requested_value="present in all Plasmodium species",
    label="presence",
    source=ConstraintSource.USER_EXPLICIT,
)


@pytest.fixture(autouse=True)
def _no_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(
        *, site_id: str, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, search_names
        return {}

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)


@pytest.fixture
def validated(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The site refuses the 90 percent reading and spells the others as written,
    with single spaces."""
    sent: list[str] = []

    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        wire = parameters[_EXPRESSION].to_wire()
        sent.append(wire)
        if " ".join(wire.split()) == SHARE and wire != _SPACED:
            raise ValidationError(_REFUSAL)
        return ValidatedParams(
            params={
                **parameters,
                _EXPRESSION: StringValue(value=" ".join(wire.split())),
            }
        )

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)
    return sent


def _criterion(**fields: object) -> Criterion:
    return Criterion.model_validate(
        {
            "id": "c_plas",
            "text": "present in all Plasmodium species",
            "searchName": _SEARCH,
            "recordClass": "group",
            "resolvedParams": {
                _EXPRESSION: BoundValue(value=StringValue(value=EVERY), source="chosen")
            },
        }
        | fields
    )


def _question(
    *readings: Reading, requirements: list[str] | None = None
) -> SlotQuestion:
    return SlotQuestion(
        question="Present in which Plasmodium genomes?",
        recommended_value="Every one of the 61 genomes",
        criterion_id="c_plas",
        param_name=_EXPRESSION,
        requirements=["R1"] if requirements is None else requirements,
        readings=list(readings),
    )


async def _held(question: SlotQuestion, criterion: Criterion) -> FrameResult | object:
    state = AgentToolState(
        operational_spec_draft=OperationalSpec(criteria=[criterion]),
        stated_requirements=[_PRESENT],
    )
    return await hold_the_readings_to_the_site(
        agent_run_context(agent_state=state),
        FrameResult(disposition="needs_user", open_questions=[question]),
    )


async def test_a_reading_the_site_refuses_goes_back_with_the_site_s_words(
    validated: list[str],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await _held(
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label=_SHARE_LABEL, value=SHARE),
            ),
            _criterion(),
        )

    assert _SHARE_LABEL in str(refused.value)
    assert _REFUSAL in str(refused.value)
    assert validated == [EVERY, SHARE]


async def test_a_reading_the_site_validates_reaches_the_card_in_the_site_s_spelling(
    validated: list[str],
) -> None:
    held = await _held(
        _question(
            Reading(label="Every one of the 61 genomes", value=EVERY),
            Reading(label=_SHARE_LABEL, value=_SPACED),
        ),
        _criterion(),
    )

    assert held == FrameResult(
        disposition="needs_user",
        open_questions=[
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label=_SHARE_LABEL, value=SHARE),
            )
        ],
    )


@pytest.mark.parametrize(
    "kind",
    [
        "single-pick-vocabulary",
        "multi-pick-vocabulary",
        "filter",
        "input-dataset",
        "input-step",
    ],
)
async def test_a_reading_on_a_parameter_that_is_no_free_text_or_range_goes_back(
    validated: list[str], kind: ParamKind
) -> None:
    criterion = _criterion(
        resolvedParams={},
        openParams=[
            OpenSlot(criterion_id="c_plas", param_name=_EXPRESSION, param_kind=kind)
        ],
    )

    with pytest.raises(ModelRetry, match=f"takes {kind}"):
        await _held(
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label="Most of them", value=_SPACED),
            ),
            criterion,
        )

    assert validated == []


async def test_a_reading_naming_a_requirement_the_list_lacks_goes_back(
    validated: list[str],
) -> None:
    with pytest.raises(ModelRetry, match="R7"):
        await _held(
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label="Most of them", value=_SPACED),
                requirements=["R7"],
            ),
            _criterion(),
        )


async def test_a_question_that_names_no_requirement_goes_back_in_one_sentence(
    validated: list[str],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await _held(
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label="Most of them", value=_SPACED),
                requirements=[],
            ),
            _criterion(),
        )

    assert str(refused.value) == (
        "Change these readings, or ask nothing about them and say why in "
        "summary: c_plas.phyletic_expression: name in the question's "
        "`requirements` the keys of the requirements its readings approximate, "
        "from R1."
    )


async def test_a_key_spelled_without_its_letter_goes_back_with_the_keys_held(
    validated: list[str],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await _held(
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label="Most of them", value=_SPACED),
                requirements=["1"],
            ),
            _criterion(),
        )

    assert str(refused.value) == (
        "Change these readings, or ask nothing about them and say why in "
        "summary: c_plas.phyletic_expression: replace ['1'] in the question's "
        "`requirements` with keys the requirement list holds, from R1."
    )


async def test_a_question_with_no_keys_reaches_the_card_when_none_were_stated(
    validated: list[str],
) -> None:
    question = _question(
        Reading(label="Every one of the 61 genomes", value=EVERY),
        Reading(label="Most of them", value=_SPACED),
        requirements=[],
    )
    state = AgentToolState(
        operational_spec_draft=OperationalSpec(criteria=[_criterion()]),
    )

    held = await hold_the_readings_to_the_site(
        agent_run_context(agent_state=state),
        FrameResult(disposition="needs_user", open_questions=[question]),
    )

    assert held == FrameResult(
        disposition="needs_user",
        open_questions=[
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label="Most of them", value=SHARE),
                requirements=[],
            )
        ],
    )


async def _picked(label: str) -> LeadDeps:
    question = _question(
        Reading(label="Every one of the 61 genomes", value=EVERY),
        Reading(label=_SHARE_LABEL, value=SHARE),
    ).typed(_criterion(), noun="group")
    deps = lead_deps(
        pipeline_state(
            "orthomcl",
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(criteria=[_criterion()]),
                open_questions=[question],
            ),
        )
    )
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=[label]
            )
        ]
    }
    await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([question]),
        reply="Two readings.",
    )
    return deps


def _bound(deps: LeadDeps) -> list[tuple[ParamValue, str | None]]:
    spec = deps.state.domain.operational_spec
    assert spec is not None
    return [
        (
            c.resolved_params[_EXPRESSION].value,
            None if c.held_reading is None else c.held_reading.reading,
        )
        for c in spec.criteria
    ]


async def test_a_picked_reading_the_site_refuses_binds_nothing(
    validated: list[str],
) -> None:
    deps = await _picked(_SHARE_LABEL)

    assert _bound(deps) == [(StringValue(value=EVERY), None)]
    answered = deps.state.turn_markers.answered
    assert answered is not None
    assert f"the site refused {_SHARE_LABEL!r}, so it binds nothing: {_REFUSAL}" in (
        answered.answer
    )


_UNAVAILABLE = WDKError("Service Unavailable", status=503)


@pytest.fixture
def unanswered(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del parameters, callbacks
        raise _UNAVAILABLE

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


_SLOW_SECONDS = 1.0
_AS_WRITTEN = _question(
    Reading(label="Every one of the 61 genomes", value=EVERY),
    Reading(label=_SHARE_LABEL, value=_SPACED),
)


async def test_a_reading_the_site_did_not_answer_reaches_the_card_as_written(
    unanswered: None,
) -> None:
    assert await _held(_AS_WRITTEN, _criterion()) == FrameResult(
        disposition="needs_user", open_questions=[_AS_WRITTEN]
    )


async def test_a_reading_the_site_answered_too_slowly_reaches_the_card_as_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _slow(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        await asyncio.sleep(_SLOW_SECONDS)
        wire = parameters[_EXPRESSION].to_wire()
        return ValidatedParams(
            params={
                **parameters,
                _EXPRESSION: StringValue(value=" ".join(wire.split())),
            }
        )

    monkeypatch.setattr(reading_check, "validate_parameters", _slow)
    monkeypatch.setattr(reading_check, "CHECK_BUDGET_SECONDS", 0.01)
    started = time.monotonic()

    held = await _held(_AS_WRITTEN, _criterion())

    assert held == FrameResult(disposition="needs_user", open_questions=[_AS_WRITTEN])
    assert time.monotonic() - started < _SLOW_SECONDS / 2


async def test_a_pick_the_site_did_not_check_binds_its_reading(
    unanswered: None,
) -> None:
    deps = await _picked(_SHARE_LABEL)

    assert _bound(deps) == [(StringValue(value=SHARE), _SHARE_LABEL)]


async def test_two_readings_the_site_spells_alike_go_back(
    validated: list[str],
) -> None:
    with pytest.raises(ModelRetry, match="two readings bind one value"):
        await _held(
            _question(
                Reading(label="Every one of the 61 genomes", value=EVERY),
                Reading(label="All 61 genomes", value="PLAS=61T  AND  TOXO=0T"),
            ),
            _criterion(),
        )


async def test_a_reading_question_that_names_no_slot_is_named_by_its_words() -> None:
    question = SlotQuestion(
        question="Present in which genomes?",
        readings=[
            Reading(label="Every one of the 61 genomes", value=EVERY),
            Reading(label="Most of them", value=SHARE),
        ],
    )

    with pytest.raises(ModelRetry) as refused:
        await _held(question, _criterion())

    assert str(refused.value) == (
        "Change these readings, or ask nothing about them and say why in summary: "
        "the question 'Present in which genomes?' offers the readings ['Every one "
        "of the 61 genomes', 'Most of them']: name the `criterion_id` and "
        "`param_name` its readings set."
    )
