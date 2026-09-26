"""A bare count of controls in a reply is the size of a list the turn holds."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests, ToolDenied

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.evidence_claims import ListClaim, list_claims
from pathfinder.ai.lead.turn_contract import (
    CONTRACT_HEADING,
    LeadResponse,
    Mismatch,
    reconcile,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.tools.standalone.separation import SEPARATION
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.separation import TASK_ID, recorded_offer
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_POSITIVES = [f"PF3D7_{n:07d}" for n in range(1000100, 1000180)]
_NEGATIVES = [f"PF3D7_{n:07d}" for n in range(1400100, 1400140)]
_V4_REPLY = (
    "I will search for the strategy that separates your lists, using the {n} "
    "positive controls and the 40 negative controls you gave."
)


def _v4_card(reply: str) -> list[str]:
    """The paragraphs of the denial of the V4 separation card, or none when shown."""
    deps = lead_deps(pipeline_state(user_prompt="Separate these controls."))
    call = ToolCallPart(
        tool_name=SEPARATION.tool_name,
        args={
            "reply": reply,
            "positive_controls": _POSITIVES,
            "negative_controls": _NEGATIVES,
            "mode": "exact",
        },
        tool_call_id="call_separate",
    )
    results = hold_the_contract_on_a_card(
        run_context_for(deps), DeferredToolRequests(approvals=[call])
    )
    if results is None:
        return []
    denial = TypeAdapter(ToolDenied).validate_python(results.approvals["call_separate"])
    return denial.message.split("\n\n")


@pytest.mark.parametrize("stated", [78, 81])
def test_the_v4_card_that_misstates_the_positives_is_denied(stated: int) -> None:
    assert _v4_card(_V4_REPLY.format(n=stated)) == [
        CONTRACT_HEADING,
        (
            f"Your reply says {stated} positive controls; the lists this turn "
            "holds are 80 positive and 40 negative controls. Return the same "
            "reply with each list stated at the size the turn holds."
        ),
        "The card was not shown to the researcher. Answer again with the card.",
    ]


def test_the_v4_card_that_states_the_call_s_lists_is_shown() -> None:
    assert _v4_card(_V4_REPLY.format(n=80)) == []


def _misstated(
    prose: str, state_domain: StrategyDomainState | None = None
) -> list[Mismatch]:
    state = pipeline_state(user_prompt="How did it go?", user_message_id=uuid4())
    if state_domain is not None:
        state.domain = state_domain
    deps = lead_deps(state)
    record = turn_record(run_context_for(deps), card_offer=str(TASK_ID))
    found = reconcile(LeadResponse(prose=prose, strategy_changed=False), record)
    return [m for m in found if m.kind == "misstated_control_list"]


def _resumed_after_a_separation() -> StrategyDomainState:
    offer = recorded_offer()
    return StrategyDomainState(separation_offers={offer.task_id: offer})


def test_the_resumed_turn_states_the_offer_s_list_size() -> None:
    domain = _resumed_after_a_separation()

    assert _misstated("It scored the 80 positive controls.", domain) == []
    (refused,) = _misstated("It scored the 81 positive controls.", domain)
    assert refused.sentence.startswith(
        "Your reply says 81 positive controls; the lists this turn holds are 80 "
        "positive and 40 negative controls."
    )


def _runs(positives: int, negatives: int) -> list[ControlTestRun]:
    """A control test that returned this many of 80 positives and 40 negatives."""
    return [
        ControlTestRun(
            tool_call_id="call_controls",
            evidence=ControlTestEvidence(
                tested_label="Invasion",
                wdk_step_id=440299573,
                positive=ControlSetEvidence(
                    returned=_POSITIVES[:positives],
                    not_returned=_POSITIVES[positives:],
                ),
                negative=ControlSetEvidence(
                    returned=_NEGATIVES[:negatives],
                    not_returned=_NEGATIVES[negatives:],
                ),
            ),
        )
    ]


def _tested(prose: str, positives: int = 52, negatives: int = 2) -> list[str]:
    state = pipeline_state(user_prompt="Test my controls.", user_message_id=uuid4())
    state.turn_markers.record_control_tests(_runs(positives, negatives))
    record = turn_record(run_context_for(lead_deps(state)))
    found = reconcile(LeadResponse(prose=prose, strategy_changed=False), record)
    return [m.kind for m in found if m.kind == "misstated_control_list"]


def _v2_mismatches(prose: str) -> list[str]:
    return _tested(prose)


@pytest.mark.parametrize(
    "prose",
    [
        "I kept the 75 positive controls the strategy returned.",
        "The strategy contains 75 positives.",
        "It includes 75 positive controls and excludes 5.",
        "The top 20 positives rank above every negative.",
        "I list the 3 negatives that slipped in.",
    ],
)
def test_a_result_stated_as_a_bare_count_passes(prose: str) -> None:
    assert _tested(prose, positives=75, negatives=3) == []


@pytest.mark.parametrize(
    "prose",
    [
        "I kept the 81 positive controls the strategy returned.",
        "The strategy contains 77 positives.",
        "I list the 4 negatives that slipped in.",
    ],
)
def test_a_count_neither_a_list_nor_a_result_is_refused(prose: str) -> None:
    assert _tested(prose, positives=75, negatives=3) == ["misstated_control_list"]


def test_v2_states_the_control_test_s_list_sizes() -> None:
    assert (
        _v2_mismatches("I tested against 80 positive and 40 negative controls.") == []
    )
    assert _v2_mismatches("I tested against 81 positive and 40 negative controls.") == [
        "misstated_control_list"
    ]


def test_a_turn_that_holds_no_list_reads_no_list_claim() -> None:
    assert _misstated("You pasted 80 positive controls.") == []


@pytest.mark.parametrize(
    ("prose", "claims"),
    [
        ("using the 78 positive controls", [ListClaim(stated=78, kind="positive")]),
        (
            "with 81 positives and 40 negatives",
            [
                ListClaim(stated=81, kind="positive"),
                ListClaim(stated=40, kind="negative"),
            ],
        ),
        ("all 40 negative controls", [ListClaim(stated=40, kind="negative")]),
        ("52 of 80 positive controls returned", []),
        ("52 of the 80 positives", []),
        ("It recovered 75 positive controls", [ListClaim(stated=75, kind="positive")]),
        ("The top 20 positives rank first", []),
        (
            "Of the 81 positive controls, 75 were returned",
            [
                ListClaim(stated=81, kind="positive"),
            ],
        ),
    ],
)
def test_a_list_claim_is_a_bare_count_of_one_kind(
    prose: str, claims: list[ListClaim]
) -> None:
    assert list_claims(prose) == claims
