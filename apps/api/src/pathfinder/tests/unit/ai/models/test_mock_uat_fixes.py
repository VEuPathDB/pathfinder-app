"""The arcs meet what the UAT flows expect of them, on plasmodb and vectorbase."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import SheetEntry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_sheets
from pathfinder.ai.models.mock.growths import orthologs_criterion
from pathfinder.ai.models.mock.sheets import richest_value
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionReply, criterion_call
from pathfinder.ai.models.mock.strategy_specs import intersect_spec
from pathfinder.tests.unit.ai.models._mock_pins import (
    edit_order,
    framed_pins,
    unframed_pins,
)
from pathfinder.tests.unit.ai.models._mock_turns import (
    LIVE_ROOT_COUNT,
    OWN_EXPERIMENT_SEARCH,
    SAVED_GENE_COUNT,
    SHEET_ORGANISMS,
    Scene,
    args_of,
    names,
    play,
    verify_order,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

SITES = ("plasmodb", "vectorbase")
_ORDER = "Frame work order: mock frame"
_BUILD = [
    "classify_user_intent",
    "frame_problem",
    "build_strategy",
    "verify_strategy",
    "get_live_strategy_state",
    "final_result",
]
_CHECK = [
    "classify_user_intent",
    "verify_strategy",
    "get_live_strategy_state",
    "final_result",
]


@pytest.mark.parametrize("site_id", SITES)
def test_a_thread_framed_by_this_turn_builds_the_zero_search(site_id: str) -> None:
    scene = Scene(instructions=unframed_pins(), later_instructions=framed_pins())

    calls = play(
        "lead", site_id, "30 to 99 domains [[arc:zero-then-relax]]", scene=scene
    )

    assert names(calls) == _BUILD


@pytest.mark.parametrize("site_id", SITES)
def test_the_controls_test_on_a_built_thread_checks_the_strategy(site_id: str) -> None:
    scene = Scene(instructions=framed_pins())

    calls = play("lead", site_id, "Test it [[arc:controls-test]]", scene=scene)

    assert names(calls) == _CHECK
    assert calls[0].args_as_dict()["intent"]["classification"] == "extend_strategy"


@pytest.mark.parametrize("site_id", SITES)
def test_a_proposal_whose_sheet_is_not_pinned_reopens_the_sheet(site_id: str) -> None:
    there = orthologs_criterion(
        SiteValues.for_site(site_id), "orthologs_there", syntenic="yes"
    )
    opened = CriterionReply(
        criterion_id="orthologs_there",
        search_name=there.search_name,
        params_template={"organism": None},
    )

    call = criterion_call(there, [opened], "")

    assert call is not None
    assert call.args_as_dict() == {
        "criterion_id": "orthologs_there",
        "text": there.text,
        "search_name": "GenesByOrthologs",
        "role": "transform",
    }


@pytest.mark.parametrize("site_id", SITES)
def test_an_open_slot_is_answered_with_its_first_option(site_id: str) -> None:
    crit = intersect_spec(SiteValues.for_site(site_id)).criteria[0]
    bound = CriterionReply.model_validate(
        {
            "criterionId": crit.criterion_id,
            "searchName": crit.search_name,
            "resolvedParams": {"signalp_version": "SignalP-6.0"},
            "openSlots": [{"paramName": "organism", "options": ["first", "second"]}],
        }
    )

    call = criterion_call(crit, [bound], "")

    assert call is not None
    assert call.args_as_dict()["params"] == {
        "signalp_version": "SignalP-6.0",
        "organism": ["first"],
    }


@pytest.mark.parametrize("site_id", SITES)
def test_the_saved_gene_set_reply_states_its_count(site_id: str) -> None:
    text = "Save these as a gene set named UAT G1. [[arc:save-gene-set]]"

    calls = play("lead", site_id, text)

    assert (
        calls[-1]
        .args_as_dict()["prose"]
        .startswith(f"Saved as the gene set UAT G1 with {SAVED_GENE_COUNT} genes.")
    )


@pytest.mark.parametrize("site_id", SITES)
def test_a_search_no_site_search_states_is_named(site_id: str) -> None:
    text = "Find genes with a predicted GPI anchor [[arc:no-search-states-it]]"

    calls = play("frame", site_id, text, work_order=_ORDER)

    assert calls[-1].args_as_dict()["summary"] == (
        f"No search on {site_id} states: Find genes with a predicted GPI anchor."
    )


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("arc", ["single", "intersect", "count-question"])
def test_a_build_finds_searches_by_the_request_first(arc: str, site_id: str) -> None:
    calls = play(
        "frame", site_id, f"Find signal genes [[arc:{arc}]]", work_order=_ORDER
    )

    assert names(calls)[:2] == ["search_for_searches", "list_searches"]
    assert args_of(calls, "search_for_searches") == [{"query": "Find signal genes"}]


@pytest.mark.parametrize("site_id", SITES)
def test_a_ranked_own_experiment_is_bound_and_built(site_id: str) -> None:
    text = "Upregulated after a blood meal [[arc:other-site-experiment]]"

    frame = play("frame", site_id, text, work_order=_ORDER)
    lead = play("lead", site_id, text)

    assert names(frame) == [
        "list_searches",
        "search_for_searches",
        "set_criterion",
        "set_criterion",
        "set_structure",
        "final_result",
    ]
    assert args_of(frame, "set_criterion")[0]["search_name"] == OWN_EXPERIMENT_SEARCH
    assert names(lead) == _BUILD


@pytest.mark.parametrize("site_id", SITES)
def test_no_own_search_at_all_reads_the_other_site_and_builds_nothing(
    site_id: str,
) -> None:
    ranked = [
        {"note": f"No search on {site_id} matched the request."},
        {"otherSites": {"experiments": [{"datasetId": "DS_elsewhere"}]}},
    ]
    unbound = {"summary": "It runs on another site.", "disposition": "needs_research"}
    text = "Upregulated after a blood meal [[arc:other-site-experiment]]"

    frame = play(
        "frame",
        site_id,
        text,
        work_order=_ORDER,
        scene=Scene(answers={"search_for_searches": ranked}),
    )
    lead = play("lead", site_id, text, scene=Scene(answers={"frame_problem": unbound}))

    assert names(frame) == [
        "list_searches",
        "search_for_searches",
        "read_experiment",
        "final_result",
    ]
    assert names(lead) == ["classify_user_intent", "frame_problem", "final_result"]
    assert (
        lead[-1].args_as_dict()["prose"] == "It runs on another site. I built nothing."
    )


def test_the_portal_intersects_the_two_searches_a_component_site_does() -> None:
    spec = intersect_spec(SiteValues.for_site("veupathdb"))

    assert [c.search_name for c in spec.criteria] == [
        "GenesWithSignalPeptide",
        "GenesByTransmembraneDomains",
    ]


@pytest.mark.parametrize("site_id", SITES)
def test_the_portal_route_names_a_portal_organism_the_sheet_does_not_reach(
    site_id: str,
) -> None:
    calls = play("frame", site_id, "[[arc:portal-only]]", work_order=_ORDER)

    proposed = [a for a in args_of(calls, "set_criterion") if "params" in a]
    organism = proposed[0]["params"]["organism"]
    assert organism == [SiteValues.for_site(site_id).portal_organisms[0]]
    assert organism[0] not in SHEET_ORGANISMS[site_id]


def test_a_sheet_value_is_the_term_the_site_annotates_most() -> None:
    state = AgentToolState()
    labels = {
        "GO:0047316": "GO:0047316 : transaminase activity : 7",
        "GO:0004672": "GO:0004672 : protein kinase activity : 143",
        "GO:0016301": "GO:0016301 : kinase activity : 12",
    }
    entry = SheetEntry(
        name="go_typeahead",
        display_name="GO term",
        type="multi-pick-vocabulary",
        required=True,
        vocabulary=[VocabOption(value=v, display=d) for v, d in labels.items()],
    )
    state.pin_sheet("go_genes", "GenesByGoTerm", [entry], what_runs="GO")
    pinned = pinned_frame_sheets(agent_run_context(agent_state=state)) or ""

    assert richest_value(pinned, "go_genes", "go_typeahead") == "GO:0004672"


_EMPTY_STEP = {"stepId": "step_tm", "displayName": "Transmembrane Domain Count"}


@pytest.mark.parametrize("site_id", SITES)
def test_the_recap_names_each_step_that_returns_nothing(site_id: str) -> None:
    live = {
        "rootCount": 0,
        "steps": [
            {**_EMPTY_STEP, "estimatedSize": 0},
            {"stepId": "step_sp", "displayName": "Signal Peptide", "estimatedSize": 12},
        ],
    }
    scene = Scene(answers={"get_live_strategy_state": live})

    calls = play("lead", site_id, "Diagnose it [[arc:recap]]", scene=scene)

    assert (
        calls[-1]
        .args_as_dict()["prose"]
        .endswith(
            "The strategy returns 0 genes. "
            "The step 'Transmembrane Domain Count' returns 0 genes."
        )
    )


@pytest.mark.parametrize("site_id", SITES)
def test_the_zero_search_asks_for_99_domains_and_relaxes_to_15(site_id: str) -> None:
    built = play("frame", site_id, "[[arc:zero-then-relax]]", work_order=_ORDER)
    relaxed = play(
        "frame", site_id, "[[arc:zero-then-relax]]", work_order=edit_order(site_id)
    )

    first = next(a for a in args_of(built, "set_criterion") if "params" in a)
    second = next(a for a in args_of(relaxed, "set_criterion") if "params" in a)
    assert (first["params"]["min_tm"], first["params"]["max_tm"]) == ("99", "99")
    assert second["params"]["min_tm"] == "15"


@pytest.mark.parametrize("site_id", SITES)
def test_the_controls_check_states_the_controls_it_tested(site_id: str) -> None:
    outcome = {
        "status": "succeeded",
        "result": {
            "positiveRecoveredIds": ["a", "b", "c"],
            "positiveMissedIds": ["d"],
            "negativeAdmittedIds": ["e"],
            "negativeExcludedIds": ["f", "g"],
        },
    }
    scene = Scene(answers={"run_control_tests_on_step": outcome})

    verify = play(
        "verification",
        site_id,
        "Test it [[arc:controls-test]]",
        work_order=verify_order(12),
        scene=scene,
    )

    assert verify[-1].args_as_dict()["digest"]["prose"] == (
        "3 of 4 positive controls recovered; 1 of 3 negative controls returned."
    )


@pytest.mark.parametrize("site_id", SITES)
def test_the_controls_reply_is_the_check_prose(site_id: str) -> None:
    digest = {
        "digest": {"success": True, "prose": "3 of 4 positive controls recovered."}
    }
    scene = Scene(instructions=framed_pins(), answers={"verify_strategy": digest})

    calls = play("lead", site_id, "Test it [[arc:controls-test]]", scene=scene)

    assert calls[-1].args_as_dict()["prose"] == (
        f"3 of 4 positive controls recovered. The strategy returns {LIVE_ROOT_COUNT:,} genes."
    )


@pytest.mark.parametrize("site_id", SITES)
def test_the_own_top_hit_is_bound_after_a_faint_ranking_note(site_id: str) -> None:
    ranked = [
        {"note": f"No search on {site_id} states the request closely."},
        {"name": OWN_EXPERIMENT_SEARCH},
        {"otherSites": {"experiments": [{"datasetId": "DS_elsewhere"}]}},
    ]
    text = "Upregulated after a blood meal [[arc:other-site-experiment]]"

    frame = play(
        "frame",
        site_id,
        text,
        work_order=_ORDER,
        scene=Scene(answers={"search_for_searches": ranked}),
    )

    bound = [a for a in args_of(frame, "set_criterion") if "params" in a]
    assert bound[0]["search_name"] == OWN_EXPERIMENT_SEARCH
    assert "read_experiment" not in names(frame)


def test_the_portal_carries_orthologs_to_another_genus() -> None:
    calls = play("frame", "veupathdb", "[[arc:syntenic-orthologs]]", work_order=_ORDER)

    bound = [
        a
        for a in args_of(calls, "set_criterion")
        if a["criterion_id"] == "orthologs" and "params" in a
    ]
    assert bound[0]["params"]["organism"] == ["Toxoplasma gondii ME49"]


@pytest.mark.parametrize("site_id", SITES)
def test_a_component_site_carries_orthologs_within_the_genus(site_id: str) -> None:
    calls = play("frame", site_id, "[[arc:syntenic-orthologs]]", work_order=_ORDER)

    bound = [
        a
        for a in args_of(calls, "set_criterion")
        if a["criterion_id"] == "orthologs" and "params" in a
    ]
    assert bound[0]["params"]["organism"] == [SHEET_ORGANISMS[site_id][1]]
