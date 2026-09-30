"""The consult arc's FRAME leaves the organism open and asks it with the
options its sheet offers, then binds the organism the answer chose."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests.unit.ai.models._mock_turns import (
    SHEET_ORGANISMS,
    args_of,
    names,
    play,
)

SITES = ("plasmodb", "vectorbase")
_ORDER = "Frame work order: mock frame"
_QUESTION = "Which organism should the signal peptide search read?"


def _answered(organism: str) -> str:
    return (
        "FRAME work order: the previous pass ended with a question the "
        f"researcher has now answered.\nQuestion asked: {_QUESTION}\n"
        f'Answer: "{_QUESTION}" -> Organism {organism} (sets organism to "{organism}")'
    )


@pytest.mark.parametrize("site_id", SITES)
def test_the_first_pass_leaves_the_organism_open_and_asks_it(site_id: str) -> None:
    calls = play("frame", site_id, "[[arc:consult]]", work_order=_ORDER)
    bound = [a["params"] for a in args_of(calls, "set_criterion") if "params" in a]
    asked = calls[-1].args_as_dict()

    assert names(calls) == [
        "search_for_searches",
        "list_searches",
        "set_criterion",
        "set_criterion",
        "set_structure",
        "final_result",
    ]
    assert [params["organism"] for params in bound] == [None]
    assert (asked["disposition"], asked["openQuestions"]) == (
        "needs_user",
        [
            {
                "question": _QUESTION,
                "dimension": "organism",
                "recommendedValue": SiteValues.for_site(site_id).organism,
                "criterionId": "signal_peptide",
                "paramName": "organism",
                "options": [
                    SiteValues.for_site(site_id).organism,
                    *(
                        o
                        for o in SHEET_ORGANISMS[site_id]
                        if o != SiteValues.for_site(site_id).organism
                    ),
                ],
            }
        ],
    )


@pytest.mark.parametrize("site_id", SITES)
def test_the_answered_pass_binds_the_organism_the_answer_chose(site_id: str) -> None:
    chosen = SHEET_ORGANISMS[site_id][1]

    calls = play("frame", site_id, "[[arc:consult]]", work_order=_answered(chosen))
    bound = [a["params"] for a in args_of(calls, "set_criterion") if "params" in a]
    answer = calls[-1].args_as_dict()

    assert names(calls) == [
        "search_for_searches",
        "list_searches",
        "set_criterion",
        "set_criterion",
        "set_structure",
        "final_result",
    ]
    assert [params["organism"] for params in bound] == [[chosen]]
    assert (answer["disposition"], answer["changes"]) == (
        "spec_ready",
        [{"criterionId": "signal_peptide", "disposition": "changed"}],
    )
