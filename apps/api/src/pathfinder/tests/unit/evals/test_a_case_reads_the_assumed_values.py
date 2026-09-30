"""A case states how many applied values the request did not state, the gap rows
the check may leave, and the phrases a reply of an earlier turn must carry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from pathfinder.evals.difference import CaseDifference
from pathfinder.evals.scoring import (
    ObservedOutcome,
    RequirementCounts,
    score_case,
)
from pathfinder.evals.summary import CaseResult, EvalRunSummary


def _case(expected: ExpectedOutcome, *turns: str) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=list(turns) or ["P. falciparum 3D7 genes with a signal peptide"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the assumed values",
        expected=expected,
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-09-28",
        ),
    )


def test_a_run_that_applied_an_unstated_value_is_named_on_assumed_stated() -> None:
    case = _case(ExpectedOutcome(builds_strategy=True, assumed_stated=0))

    score = score_case(case, ObservedOutcome(built_strategy=True, assumed=2))

    assert score.differences == [
        CaseDifference(field="assumedStated", expected="0", actual="2")
    ]


def test_assumed_values_are_compared_only_when_the_run_counted_them() -> None:
    case = _case(ExpectedOutcome(builds_strategy=True, assumed_stated=0))

    scores = [
        score_case(case, ObservedOutcome(built_strategy=True, assumed=assumed))
        for assumed in (None, 0)
    ]

    assert [score.passed for score in scores] == [True, True]


def test_the_gap_rows_no_search_states_are_compared_like_the_unmet_rows() -> None:
    case = _case(ExpectedOutcome(builds_strategy=True, unexpressed_requirements=0))

    scores = [
        score_case(case, ObservedOutcome(built_strategy=True, requirements=counted))
        for counted in (RequirementCounts(met=4, unexpressed=1), None)
    ]

    assert [score.differences for score in scores] == [
        [CaseDifference(field="unexpressedRequirements", expected="0", actual="1")],
        [CaseDifference(field="unexpressedRequirements", expected="0", actual="None")],
    ]


def test_an_earlier_turn_reply_is_held_to_its_own_phrases() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            turn_reply_mentions={0: ["10 reads"]},
            turn_reply_omits={0: ["734.0197714535435"]},
        ),
        "Raise the fold change to 4-fold.",
        "Which kinases remain?",
    )
    observed = ObservedOutcome(
        built_strategy=True,
        turn_replies=["The floor is 734.0197714535435.", "Three kinases remain."],
        reply_text="Three kinases remain.",
    )

    score = score_case(case, observed)

    assert score.differences == [
        CaseDifference(
            field="turnReplyMentions.0",
            expected="10 reads",
            actual="The floor is 734.0197714535435.",
            read="the facts part and the reply",
        ),
        CaseDifference(
            field="turnReplyOmits.0",
            expected="734.0197714535435",
            actual="The floor is 734.0197714535435.",
            read="the reply",
        ),
    ]


def test_an_earlier_turn_reply_that_carries_its_phrases_passes() -> None:
    case = _case(
        ExpectedOutcome(builds_strategy=True, turn_reply_mentions={0: ["10 reads"]}),
        "Raise the fold change to 4-fold.",
        "Which kinases remain?",
    )
    observed = ObservedOutcome(
        built_strategy=True,
        turn_replies=["The floor is the site's 10 reads.", "Three remain."],
    )

    assert score_case(case, observed).passed is True


def test_a_turn_the_run_never_reached_reads_as_an_empty_reply() -> None:
    case = _case(
        ExpectedOutcome(builds_strategy=True, turn_reply_mentions={1: ["216"]}),
        "Find the VSP genes.",
        "How many have a signal peptide?",
    )

    score = score_case(case, ObservedOutcome(built_strategy=True, turn_replies=["x"]))

    assert score.differences == [
        CaseDifference(
            field="turnReplyMentions.1",
            expected="216",
            actual="",
            read="the facts part and the reply",
        )
    ]


def test_a_turn_phrase_names_a_turn_the_case_has() -> None:
    with pytest.raises(ValidationError, match="turn 2"):
        _case(
            ExpectedOutcome(builds_strategy=True, turn_reply_omits={2: ["uuid"]}),
            "first",
            "second",
        )


def test_the_turn_phrases_are_de_identified_text() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True, turn_reply_mentions={0: ["ada@example.org"]}
        ),
    )

    with pytest.raises(ValueError, match="email"):
        case.assert_de_identified()


def test_the_run_totals_the_assumed_values_its_cases_counted() -> None:
    def summary(*assumed: int | None) -> EvalRunSummary:
        return EvalRunSummary(
            harness="pydantic-evals",
            provider="mock",
            assistant_id="pathfinder",
            ran_at="2026-09-28T00:00:00+00:00",
            cases=[
                CaseResult(name=f"c{i}", verdict="pass", assumed=value)
                for i, value in enumerate(assumed)
            ],
        )

    counted = summary(0, 2, None).model_dump(by_alias=True, mode="json")
    uncounted = summary(None).model_dump(by_alias=True, mode="json")

    assert (counted["assumed"], [c["assumed"] for c in counted["cases"]]) == (
        2,
        [0, 2, None],
    )
    assert uncounted["assumed"] is None
