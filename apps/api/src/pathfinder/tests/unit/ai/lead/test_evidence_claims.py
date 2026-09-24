"""A control count or a control gene id in prose is held to the tests the turn ran."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.evidence_claims import (
    CountClaim,
    control_claims,
    unbacked_claims,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, hold_the_turn_contract
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_TESTED = (
    ControlTestEvidence(
        tested_label="Kinases",
        wdk_step_id=440299573,
        positive=ControlSetEvidence(
            returned=[f"PF3D7_{index:07d}" for index in range(1133400, 1133407)],
            not_returned=["PF3D7_0102600", "PF3D7_0213400", "PF3D7_0303900"],
        ),
        negative=ControlSetEvidence(
            returned=["PF3D7_1200600"],
            not_returned=[f"PF3D7_{index:07d}" for index in range(1400001, 1400012)],
        ),
    ),
)


def test_a_count_the_test_recorded_is_backed() -> None:
    prose = "The strategy recovered **7** of 10 positive controls and 1/12 negatives."

    assert unbacked_claims(control_claims(prose), _TESTED) == []


def test_a_count_the_test_did_not_record_is_named_with_the_recorded_one() -> None:
    prose = "The strategy recovered **8** of 10 positive controls."

    assert unbacked_claims(control_claims(prose), _TESTED) == [
        (
            "The reply says 8 of 10 positive controls returned; the control "
            "results recorded 7 of 10 positive controls returned."
        )
    ]


def test_an_excluded_count_is_read_from_the_same_set() -> None:
    prose = "It left out 11 of the 12 negative controls."

    assert unbacked_claims(control_claims(prose), _TESTED) == []


def test_a_gene_filed_on_the_other_list_is_refused() -> None:
    prose = "Positive control `PF3D7_0102600` was recovered."

    assert unbacked_claims(control_claims(prose), _TESTED) == [
        (
            "The reply says control `PF3D7_0102600` was returned; the control test "
            "recorded it as not returned."
        )
    ]


def test_a_gene_the_reply_files_where_the_test_did_is_backed() -> None:
    prose = "Positive control `PF3D7_0102600` was not returned by the strategy."

    assert unbacked_claims(control_claims(prose), _TESTED) == []


def test_a_control_gene_no_test_holds_is_refused() -> None:
    prose = "The control `PF3D7_9999999` was recovered."

    assert unbacked_claims(control_claims(prose), _TESTED) == [
        (
            "The reply says control `PF3D7_9999999` was returned; no control "
            "result of this turn or of its last check lists it."
        )
    ]


def test_a_control_result_on_a_turn_with_no_test_is_refused() -> None:
    prose = "All 10 of 10 positive controls were recovered."

    assert unbacked_claims(control_claims(prose), ()) == [
        (
            "The reply says 10 of 10 positive controls returned, and no control "
            "result of this turn or of its last check holds positive controls."
        )
    ]


def test_prose_with_no_control_claim_names_nothing() -> None:
    prose = (
        "The strategy returns 212 kinases; `GenesByText` found `PF3D7_1133400` "
        "among them."
    )

    assert control_claims(prose) == []


@pytest.mark.parametrize(
    ("prose", "recorded"),
    [
        (
            "The strategy recovered 3 of 10 positive controls.",
            "the control results recorded 7 of 10 positive controls returned.",
        ),
        (
            "The strategy returned 11 of 12 negative controls.",
            "the control results recorded 1 of 12 negative controls returned.",
        ),
    ],
)
def test_a_count_filed_under_the_other_list_is_refused(
    prose: str, recorded: str
) -> None:
    """The verb says which list the count is read from."""
    (sentence,) = unbacked_claims(control_claims(prose), _TESTED)

    assert sentence.endswith(recorded)


def test_a_count_with_no_verb_may_name_either_list() -> None:
    claims = control_claims("Kinases: 3 of 10 positive controls (see the card).")

    assert claims == [CountClaim(stated=3, of=10, kind="positive", returned=None)]
    assert unbacked_claims(claims, _TESTED) == []


def test_a_count_of_something_that_is_not_a_control_is_no_claim() -> None:
    prose = "Of the 48 genes, 5 of 7 positive regulators of egress are present."

    assert control_claims(prose) == []


def test_a_clause_that_says_no_control_ran_files_no_gene() -> None:
    prose = "Among the 48 genes returned (no controls were run), `PF3D7_1222600` leads."

    assert control_claims(prose) == []


def test_a_vectorbase_gene_id_is_read_as_a_control_id() -> None:
    prose = "Positive control `AGAP004707` was recovered."

    assert unbacked_claims(control_claims(prose), _TESTED) == [
        (
            "The reply says control `AGAP004707` was returned; no control "
            "result of this turn or of its last check lists it."
        )
    ]


def _checked_deps() -> LeadDeps:
    """A turn that ran one control test and wrote nothing."""
    deps = lead_deps(
        pipeline_state(user_prompt="How well does it recover my controls?")
    )
    deps.state.turn_markers.intent_classified = True
    deps.state.turn_markers.record_control_tests(
        [ControlTestRun(tool_call_id="call_controls", evidence=_TESTED[0])]
    )
    return deps


def test_the_contract_refuses_an_unbacked_count_once() -> None:
    deps = _checked_deps()
    report = LeadResponse(
        prose="The strategy recovered 8 of 10 positive controls.",
        strategy_changed=False,
    )

    with pytest.raises(ModelRetry) as raised:
        hold_the_turn_contract(run_context_for(deps), report)

    assert "7 of 10 positive controls returned" in str(raised.value)
    assert "taken from the evidence card" in str(raised.value)
    assert hold_the_turn_contract(run_context_for(deps), report) is report


def test_the_contract_passes_the_recorded_numbers() -> None:
    deps = _checked_deps()
    report = LeadResponse(
        prose="The strategy recovered 7 of 10 positive controls.",
        strategy_changed=False,
    )

    assert hold_the_turn_contract(run_context_for(deps), report) is report
    assert deps.state.turn_markers.contract_refused is False
