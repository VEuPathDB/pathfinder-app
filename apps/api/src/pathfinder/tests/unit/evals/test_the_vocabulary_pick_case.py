"""The corpus case on a typeahead pick holds the family the lookup reaches."""

from __future__ import annotations

from pathfinder.evals.case import GatePlan
from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_odorant_binding_case_binds_the_obp_family_on_chromosome_3() -> None:
    case = _BY_NAME["uat-core-c-vectorbase"]
    expected = case.expected

    assert (case.turns, case.gates) == (
        ["Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3."],
        GatePlan(policy="leave"),
    )
    # The family binds as the entry whose label carries the concept's words, in
    # whichever domain database the pass reads, so the case pins no entry.
    assert (expected.parameters, expected.builds_strategy, expected.root_count) == (
        {},
        None,
        None,
    )
