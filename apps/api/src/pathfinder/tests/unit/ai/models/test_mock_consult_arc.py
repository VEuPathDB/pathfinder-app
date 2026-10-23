"""The consult arc's FRAME leaves the organism open and asks it with the
options its sheet offers, then binds the organism the answer chose."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import Tool

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.tools.standalone.catalog import list_searches, search_for_searches
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.tests.unit.ai.models._mock_turns import (
    SHEET_ORGANISMS,
    Scene,
    args_of,
    names,
    play,
)

SITES = ("plasmodb", "vectorbase")
_ORDER = "Frame work order: mock frame"
_QUESTION = "Which organism should the signal peptide search read?"


_TOOLS: dict[str, Tool[Any]] = {
    "search_for_searches": Tool(search_for_searches),
    "list_searches": Tool(list_searches),
    "set_criterion": Tool(set_criterion),
    "set_structure": Tool(set_structure),
}


def _unsent(calls: list[Any]) -> dict[str, list[str]]:
    return {
        call.tool_name: sorted(
            set(_TOOLS[call.tool_name].function_schema.json_schema.get("required", []))
            - set(call.args_as_dict())
        )
        for call in calls
        if call.tool_name in _TOOLS
    }


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
    assert _unsent(calls) == {name: [] for name in _TOOLS}
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
    assert (answer["disposition"], "changes" in answer) == ("spec_ready", False)


@pytest.mark.parametrize("site_id", SITES)
def test_a_sheet_without_the_site_organism_has_it_looked_up_and_recommended(
    monkeypatch: pytest.MonkeyPatch, site_id: str
) -> None:
    organism = SiteValues.for_site(site_id).organism
    others = [o for o in SHEET_ORGANISMS[site_id] if o != organism]
    monkeypatch.setitem(SHEET_ORGANISMS, site_id, others)
    lookup = {
        "name": "organism",
        "vocabLookup": {
            "terms": [organism],
            "matches": [
                {
                    "term": organism,
                    "phrasing": organism,
                    "reach": "every_word",
                    "values": [organism],
                }
            ],
        },
    }

    calls = play(
        "frame",
        site_id,
        "[[arc:consult]]",
        work_order=_ORDER,
        scene=Scene(answers={"get_parameter_options": lookup}),
    )
    [read] = args_of(calls, "get_parameter_options")
    [asked] = calls[-1].args_as_dict()["openQuestions"]

    assert (read["parameter_id"], read["query"]) == ("organism", [organism])
    assert asked["recommendedValue"] == organism
    assert asked["options"] == [organism, *others]
