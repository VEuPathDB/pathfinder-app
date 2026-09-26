"""The FRAME call sequence of every arc that frames, on plasmodb and on vectorbase."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests.unit.ai.models._mock_pins import edit_order
from pathfinder.tests.unit.ai.models._mock_turns import (
    SHEET_GO_TERMS,
    SHEET_ORGANISMS,
    Scene,
    args_of,
    names,
    play,
)

SITES = ("plasmodb", "vectorbase")
_ORDER = "Frame work order: mock frame"
_STRUCTURE_REFUSAL = (
    "The structure is refused: Cannot INTERSECT steps with different organism scopes."
)
_UNMATCHED = "The organism has no entry matching the value; the portal runs it."


def _bind(count: int) -> list[str]:
    return ["set_criterion"] * (2 * count)


SPEC_SEQUENCES: dict[str, list[str]] = {
    "single": [
        "search_for_searches",
        "list_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
    "intersect": [
        "search_for_searches",
        "list_searches",
        *_bind(2),
        "set_structure",
        "note",
        "pin_note",
        "final_result",
    ],
    "union": [
        "search_for_searches",
        "list_searches",
        *_bind(2),
        "set_structure",
        "final_result",
    ],
    "minus": [
        "search_for_searches",
        "list_searches",
        *_bind(2),
        "set_structure",
        "final_result",
    ],
    "orthologs": [
        "search_for_searches",
        "list_searches",
        *_bind(3),
        "set_structure",
        "final_result",
    ],
    "syntenic-orthologs": [
        "search_for_searches",
        "list_searches",
        *_bind(3),
        "set_structure",
        "final_result",
    ],
    "round-trip": [
        "search_for_searches",
        "list_searches",
        *_bind(4),
        "set_structure",
        "final_result",
    ],
    "go": [
        "search_for_searches",
        "list_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
    "count-question": [
        "search_for_searches",
        "list_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
    "combined": [
        "search_for_searches",
        "list_searches",
        *_bind(3),
        "set_structure",
        "final_result",
    ],
    "zero-then-relax": [
        "search_for_searches",
        "list_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
    "no-search-states-it": ["search_for_searches", "list_searches", "final_result"],
    "other-site-experiment": [
        "list_searches",
        "search_for_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
}
EDIT_SEQUENCES: dict[str, list[str]] = {
    "edit-param": ["list_searches", *_bind(1), "final_result"],
    "zero-then-relax": ["list_searches", *_bind(1), "final_result"],
    "add-step": ["list_searches", *_bind(1), "set_structure", "final_result"],
    "proposal": ["list_searches", *_bind(1), "set_structure", "final_result"],
    "replace-subtree": [
        "list_searches",
        *_bind(1),
        "drop_criterion",
        "set_structure",
        "final_result",
    ],
    "delete-step": ["drop_criterion", "set_structure", "final_result"],
    "orthologs": [
        "list_searches",
        "search_for_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
    "syntenic-orthologs": [
        "list_searches",
        "search_for_searches",
        *_bind(1),
        "set_structure",
        "final_result",
    ],
    "round-trip": [
        "list_searches",
        "search_for_searches",
        *_bind(2),
        "set_structure",
        "final_result",
    ],
    "portal-only": [
        "list_searches",
        "search_for_searches",
        *_bind(1),
        "final_result",
    ],
}


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("arc", sorted(SPEC_SEQUENCES))
def test_the_frame_binds_the_arc_spec(arc: str, site_id: str) -> None:
    calls = play("frame", site_id, f"[[arc:{arc}]]", work_order=_ORDER)

    assert names(calls) == SPEC_SEQUENCES[arc]


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("arc", sorted(EDIT_SEQUENCES))
def test_the_frame_edits_the_strategy_the_work_order_prints(
    arc: str, site_id: str
) -> None:
    calls = play("frame", site_id, f"[[arc:{arc}]]", work_order=edit_order(site_id))

    assert names(calls) == EDIT_SEQUENCES[arc]


@pytest.mark.parametrize("site_id", SITES)
def test_the_signal_peptide_carries_the_seed_values(site_id: str) -> None:
    seed = SiteValues.for_site(site_id).leaf("GenesWithSignalPeptide")

    calls = play("frame", site_id, "[[arc:single]]", work_order=_ORDER)

    assert seed is not None
    assert args_of(calls, "set_criterion")[1]["params"] == seed.values


@pytest.mark.parametrize("site_id", SITES)
def test_the_orthologs_target_the_second_organism_of_the_sheet(site_id: str) -> None:
    calls = play("frame", site_id, "[[arc:orthologs]]", work_order=_ORDER)

    (bound,) = [
        a
        for a in args_of(calls, "set_criterion")
        if a["criterion_id"] == "orthologs" and "params" in a
    ]
    assert bound["params"] == {
        "organism": [SHEET_ORGANISMS[site_id][1]],
        "isSyntenic": "no",
    }


def test_the_round_trip_maps_back_to_the_site_organism() -> None:
    calls = play("frame", "vectorbase", "[[arc:round-trip]]", work_order=_ORDER)

    bound = {
        a["criterion_id"]: a["params"]
        for a in args_of(calls, "set_criterion")
        if "params" in a
    }
    assert bound["orthologs_there"] == {
        "organism": ["Anopheles stephensi Indian"],
        "isSyntenic": "yes",
    }
    assert bound["orthologs_back"] == {
        "organism": ["Anopheles gambiae PEST"],
        "isSyntenic": "yes",
    }


def test_the_cross_organism_intersect_ends_on_its_refusal() -> None:
    calls = play(
        "frame",
        "plasmodb",
        "[[arc:cross-organism]]",
        work_order=_ORDER,
        scene=Scene(refused={"set_structure": _STRUCTURE_REFUSAL}),
    )

    assert names(calls) == [
        "search_for_searches",
        "list_searches",
        *_bind(2),
        "set_structure",
        "final_result",
    ]
    assert calls[-1].args_as_dict()["summary"].startswith(_STRUCTURE_REFUSAL)
    organisms = [
        a["params"]["organism"]
        for a in args_of(calls, "set_criterion")
        if "params" in a
    ]
    assert organisms == [["Plasmodium falciparum 3D7"], ["Plasmodium vivax P01"]]


def test_the_portal_only_proposal_ends_on_its_refusal() -> None:
    calls = play(
        "frame",
        "vectorbase",
        "[[arc:portal-only]]",
        work_order=_ORDER,
        scene=Scene(refused={"set_criterion": _UNMATCHED}),
    )

    assert names(calls) == [
        "list_searches",
        "search_for_searches",
        "set_criterion",
        "final_result",
    ]


def test_the_portal_only_proposal_names_another_site_organism() -> None:
    calls = play("frame", "vectorbase", "[[arc:portal-only]]", work_order=_ORDER)

    proposed = [a for a in args_of(calls, "set_criterion") if "params" in a]
    assert proposed[0]["params"]["organism"] == [
        SiteValues.for_site("vectorbase").portal_organisms[0]
    ]


@pytest.mark.parametrize(
    ("arc", "low"), [("edit-param", "1"), ("zero-then-relax", "15")]
)
def test_the_edit_moves_the_domain_minimum_and_copies_the_rest(
    arc: str, low: str
) -> None:
    calls = play(
        "frame", "vectorbase", f"[[arc:{arc}]]", work_order=edit_order("vectorbase")
    )

    bound = [a for a in args_of(calls, "set_criterion") if "params" in a]
    assert bound[0]["criterion_id"] == "tm_domains"
    assert bound[0]["params"] == {
        "organism": '["Anopheles gambiae PEST"]',
        "min_tm": low,
        "max_tm": None,
    }
    assert calls[-1].args_as_dict()["changes"] == [
        {"criterionId": "signal_peptide", "disposition": "kept"},
        {
            "criterionId": "tm_domains",
            "disposition": "changed",
            "changedParams": {"min_tm": low},
        },
    ]


def test_the_added_step_intersects_the_whole_strategy() -> None:
    calls = play(
        "frame", "plasmodb", "[[arc:add-step]]", work_order=edit_order("plasmodb")
    )

    (structure,) = args_of(calls, "set_structure")
    root = structure["root"]
    assert root["operator"] == "INTERSECT"
    assert [child.get("criterionId") for child in root["inputs"]] == [
        None,
        "added_step",
    ]
    added = [a for a in args_of(calls, "set_criterion") if "params" in a]
    assert added[0]["search_name"] == "GenesByExportPrediction"


def test_the_replacement_takes_the_place_of_the_domain_step() -> None:
    calls = play(
        "frame",
        "vectorbase",
        "[[arc:replace-subtree]]",
        work_order=edit_order("vectorbase"),
    )

    assert args_of(calls, "drop_criterion")[0]["criterion_id"] == "tm_domains"
    (structure,) = args_of(calls, "set_structure")
    children = [child["criterionId"] for child in structure["root"]["inputs"]]
    assert children == ["signal_peptide", "added_step"]


def test_the_frame_loop_asks_for_one_listing_again_and_again() -> None:
    calls = play("frame", "plasmodb", "[[arc:frame-loop]]", work_order=_ORDER, limit=3)

    assert names(calls) == ["list_searches"] * 3


def test_the_delete_closes_the_tree_over_the_step_it_drops() -> None:
    calls = play(
        "frame",
        "vectorbase",
        "[[arc:delete-step]]",
        work_order=edit_order("vectorbase"),
    )

    assert args_of(calls, "drop_criterion")[0]["criterion_id"] == "tm_domains"
    (structure,) = args_of(calls, "set_structure")
    assert structure["root"] == {
        "kind": "leaf",
        "criterionId": "signal_peptide",
        "operator": None,
        "inputs": [],
    }
    assert calls[-1].args_as_dict()["changes"] == [
        {"criterionId": "signal_peptide", "disposition": "kept"},
        {
            "criterionId": "tm_domains",
            "disposition": "dropped",
            "reason": "the request removes it",
        },
    ]


def test_the_orthologs_edit_transforms_the_whole_strategy() -> None:
    calls = play(
        "frame", "plasmodb", "[[arc:orthologs]]", work_order=edit_order("plasmodb")
    )

    (structure,) = args_of(calls, "set_structure")
    root = structure["root"]
    assert (root["kind"], root["criterionId"]) == ("transform", "orthologs")
    assert root["inputs"][0]["operator"] == "INTERSECT"
    bound = [a for a in args_of(calls, "set_criterion") if "params" in a]
    assert bound[0]["params"] == {
        "organism": ["Plasmodium vivax P01"],
        "isSyntenic": "no",
    }


def test_the_round_trip_edit_states_the_strategy_twice() -> None:
    calls = play(
        "frame", "plasmodb", "[[arc:round-trip]]", work_order=edit_order("plasmodb")
    )

    (structure,) = args_of(calls, "set_structure")
    root = structure["root"]
    held, trip = root["inputs"]
    assert root["operator"] == "INTERSECT"
    assert held["operator"] == "INTERSECT"
    assert trip["criterionId"] == "orthologs_back"
    assert trip["inputs"][0]["criterionId"] == "orthologs_there"
    assert trip["inputs"][0]["inputs"][0]["kind"] == "copy"
    assert trip["inputs"][0]["inputs"][0]["inputs"] == [held]


def test_a_site_whose_seeds_hold_no_go_term_takes_the_sheet_first_term() -> None:
    calls = play("frame", "vectorbase", "[[arc:go]]", work_order=_ORDER)

    bound = [a for a in args_of(calls, "set_criterion") if "params" in a]
    assert bound[0]["search_name"] == "GenesByGoTerm"
    assert bound[0]["params"]["go_typeahead"] == [SHEET_GO_TERMS[0]]
    assert bound[0]["params"]["organism"] == ["Anopheles gambiae PEST"]
