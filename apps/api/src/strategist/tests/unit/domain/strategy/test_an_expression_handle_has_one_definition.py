"""A handle that names no held expression is refused, in a binding and on a
card option, with the one sentence written in one place."""

from __future__ import annotations

from pathlib import Path

from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM

from strategist.ai.agents.frame_option_checks import (
    hold_an_option_to_a_held_expression,
)
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.tools.standalone._expression_handles import (
    with_stored_expressions,
)
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.domain.strategy import expression_handles
from strategist.domain.strategy.expression_handles import (
    expression_handle,
    unheld_sentence,
)
from strategist.domain.strategy.questions import SlotQuestion
from strategist.domain.strategy.readings import Reading
from strategist.tests._support.held_answers import said
from strategist.tests._support.string_literals import string_literals
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_SOURCE = Path(expression_handles.__file__).resolve().parents[2]
_UNHELD = expression_handle("pfal>=1T")


def test_a_binding_naming_an_unheld_handle_is_refused_with_the_sentence() -> None:
    state = agent_run_context().deps.agent_state
    call = CriterionCall(
        criterion_id="c_profile",
        search_name="GenesByOrthologPattern",
        text="kept in P. falciparum",
        params={PHYLETIC_EXPRESSION_PARAM: _UNHELD},
    )

    _call, problems = with_stored_expressions(state, call)

    assert problems.text().startswith(
        unheld_sentence(PHYLETIC_EXPRESSION_PARAM, [_UNHELD])
    )


def test_a_card_option_naming_an_unheld_handle_is_refused_with_the_sentence() -> None:
    question = SlotQuestion(
        question="Which pattern?",
        recommended_value=_UNHELD,
        criterion_id="c_profile",
        param_name=PHYLETIC_EXPRESSION_PARAM,
        readings=[Reading(label="kept in P. falciparum", value=_UNHELD)],
    )

    (sentence,) = said(
        hold_an_option_to_a_held_expression(
            agent_run_context(), FrameResult(open_questions=[question])
        )
    )

    assert sentence.startswith(
        unheld_sentence(f"c_profile.{PHYLETIC_EXPRESSION_PARAM}", [_UNHELD])
    )


def test_the_sentence_is_written_in_one_module() -> None:
    holding = sorted(
        str(path.relative_to(_SOURCE))
        for path in _SOURCE.rglob("*.py")
        if "tests" not in path.parts
        and any(
            "no expression of this conversation is held" in text
            for text in string_literals(path)
        )
    )

    assert holding == ["domain/strategy/expression_handles.py"]
