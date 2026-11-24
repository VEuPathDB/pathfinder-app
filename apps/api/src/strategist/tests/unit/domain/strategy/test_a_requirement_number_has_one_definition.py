"""Every argument that names a requirement by its number is refused, when the
list lacks it, with the one sentence written in one place."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelRetry

from strategist.ai.agents.frame_result_checks import (
    hold_the_reports_to_the_requirement_list,
)
from strategist.ai.lead.card_question import CardQuestion
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.lead_consult import card_stand_ins
from strategist.ai.tools.standalone._frame_answers import (
    AnsweredRequirement,
    linked_requirements,
)
from strategist.ai.tools.standalone.catalog_discovery import _requirement_words
from strategist.domain.strategy import requirement_reports
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
    unlisted_numbers_sentence,
)
from strategist.tests._support.held_answers import said
from strategist.tests._support.string_literals import string_literals
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_SOURCE = Path(requirement_reports.__file__).resolve().parents[2]


def _stated(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.UNTYPED,
        label=value,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_HELD = [_stated("secreted"), _stated("predicted GPI anchor")]


def test_the_sentence_names_the_numbers_the_list_lacks_and_holds() -> None:
    assert unlisted_numbers_sentence("answers", ["R2", "R9"], _HELD) == (
        "answers names ['R9'], which 'Requirements the researcher stated' does "
        "not hold. It holds R1, R2."
    )


def test_a_listed_number_makes_no_sentence() -> None:
    assert unlisted_numbers_sentence("answers", ["R1", "R2"], _HELD) is None


def test_a_criterion_answering_an_unlisted_number_is_refused_with_it() -> None:
    state = agent_run_context().deps.agent_state
    state.stated_requirements = list(_HELD)

    _links, problems = linked_requirements(
        state, "c_gpi", [AnsweredRequirement(requirement="R9")]
    )

    sentence = unlisted_numbers_sentence("answers", ["R9"], _HELD)
    assert sentence is not None
    assert problems.text().startswith(sentence)


def test_a_lookup_for_an_unlisted_number_is_refused_with_it() -> None:
    state = agent_run_context().deps.agent_state
    state.stated_requirements = list(_HELD)

    with pytest.raises(ModelRetry) as refused:
        _requirement_words(state, "R9")

    sentence = unlisted_numbers_sentence("requirement", ["R9"], _HELD)
    assert sentence is not None
    assert str(refused.value).startswith(sentence)


def test_a_card_replacing_an_unlisted_number_is_refused_with_it() -> None:
    card = CardQuestion(
        id="q1",
        prompt="Which stand-in?",
        dimension=ConstraintKind.UNTYPED,
        replaces=["R9"],
    )

    with pytest.raises(ModelRetry) as refused:
        card_stand_ins([card], _HELD)

    sentence = unlisted_numbers_sentence("replaces", ["R9"], _HELD)
    assert sentence is not None
    assert str(refused.value).startswith(sentence)


def test_a_report_of_an_unlisted_number_is_refused_with_it() -> None:
    ctx = agent_run_context()
    ctx.deps.agent_state.stated_requirements = list(_HELD)
    result = FrameResult(
        requirement_problems=[
            RequirementReport(
                requirement="R9", problem=RequirementProblem.SITE_HAS_NO_SEARCH
            )
        ],
    )

    (sentence,) = said(hold_the_reports_to_the_requirement_list(ctx, result))

    expected = unlisted_numbers_sentence("requirement_problems", ["R9"], _HELD)
    assert expected is not None
    assert sentence.startswith(expected)


_WORDINGS = (
    "Requirements the researcher stated' does not hold",
    "which the requirement list does not hold. ",
    "is no number of 'Requirements",
)


def _states_the_rule(path: Path) -> bool:
    return any(words in text for text in string_literals(path) for words in _WORDINGS)


def test_the_sentence_is_written_in_one_module() -> None:
    holding = sorted(
        str(path.relative_to(_SOURCE))
        for path in _SOURCE.rglob("*.py")
        if "tests" not in path.parts and _states_the_rule(path)
    )

    assert holding == ["domain/strategy/requirement_reports.py"]
