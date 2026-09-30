"""A phrase a reply must carry is read in what the turn showed, its facts part
and its reply; a phrase a reply must omit is read in the reply alone."""

from __future__ import annotations

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from pathfinder.evals.difference import CaseDifference
from pathfinder.evals.scoring import ObservedOutcome, score_case

_FACTS = "Floor =: 734.0197714535435 (10 reads) (site default)"
_REPLY = "The floor keeps genes with at least 10 reads."


def _case(expected: ExpectedOutcome) -> EvalCase:
    return EvalCase(
        name="uat-dry-b-tritrypdb",
        turns=["Kinases up 2-fold in procyclic forms.", "What floor did you use?"],
        site_id="tritrypdb",
        assistant_id="pathfinder",
        rationale="a vocabulary value is described by its label",
        expected=expected,
        provenance=CaseProvenance(
            site="tritrypdb",
            assistant="pathfinder",
            origin="uat-flow",
            reference="uat/flows-dry-uat.md#u4",
            added_at="2026-09-30",
        ),
        gates=GatePlan(policy="auto"),
    )


def _observed() -> ObservedOutcome:
    return ObservedOutcome(
        built_strategy=True,
        turn_replies=["Built.", _REPLY],
        turn_facts=["", _FACTS],
        reply_text=_REPLY,
        facts_text=_FACTS,
    )


def test_a_term_the_facts_show_beside_its_label_is_not_in_the_reply() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            turn_reply_omits={1: ["734.0197714535435"]},
            reply_omits=["734.0197714535435"],
        )
    )

    assert score_case(case, _observed()).passed is True


def test_a_phrase_the_facts_show_is_a_phrase_the_turn_mentions() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            turn_reply_mentions={1: ["site default"]},
            reply_mentions=["site default"],
        )
    )

    assert score_case(case, _observed()).passed is True


def test_each_phrase_difference_names_the_text_it_read() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            reply_mentions=["20 reads"],
            turn_reply_omits={1: ["10 reads"]},
        )
    )

    assert score_case(case, _observed()).differences == [
        CaseDifference(
            field="replyMentions",
            expected="20 reads",
            actual=f"{_FACTS}\n{_REPLY}",
            read="the facts part and the reply",
        ),
        CaseDifference(
            field="turnReplyOmits.1",
            expected="10 reads",
            actual=_REPLY,
            read="the reply",
        ),
    ]
