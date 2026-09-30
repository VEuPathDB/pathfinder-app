"""The round-4 case on a typeahead pick holds the family the lookup reaches."""

from __future__ import annotations

import datetime

from pathfinder.evals.case import GatePlan, RecordedCount
from pathfinder.evals.store import load_corpus

_BY_NAME = {case.name: case for case in load_corpus()}


def test_the_odorant_binding_case_binds_the_obp_family_on_chromosome_3() -> None:
    case = _BY_NAME["uat-dry4-c-vectorbase"]
    expected = case.expected

    assert (case.turns, case.gates) == (
        ["Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3."],
        GatePlan(policy="leave"),
    )
    assert expected.parameters == {
        "GenesByInterproDomain": {"domain_typeahead": "PF01395"},
        "GenesByLocation": {"chromosomeOptional": "3"},
    }
    assert expected.root_count == RecordedCount(
        count=39, build="71", measured_on=datetime.date(2026, 9, 30)
    )
