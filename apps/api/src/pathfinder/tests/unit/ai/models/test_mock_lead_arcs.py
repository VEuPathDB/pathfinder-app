"""The Lead's call sequence of every arc, on plasmodb and on vectorbase."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead.build_messages import build_would_replace_the_strategy
from pathfinder.ai.models.mock.edit_arcs import DELETED_PROSE
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests.unit.ai.models._mock_pins import framed_pins, memory_pins
from pathfinder.tests.unit.ai.models._mock_turns import (
    BUILT_ROOT_WDK_ID,
    CONTROL_SET_ID,
    GENE_SET_ID,
    LIVE_ROOT_COUNT,
    LIVE_ROOT_WDK_ID,
    NOT_HERE,
    Scene,
    args_of,
    built_thread,
    names,
    play,
)

SITES = ("plasmodb", "vectorbase")
COUNT_QUESTION = "How many genes does this strategy return?"
CLEAR_MESSAGE = (
    "Clear the current strategy by calling clear_strategy with confirm=true."
)
BUILD = [
    "classify_user_intent",
    "frame_problem",
    "build_strategy",
    "verify_strategy",
    "get_live_strategy_state",
    "final_result",
]
EDIT = [
    "classify_user_intent",
    "edit_strategy",
    "verify_strategy",
    "get_live_strategy_state",
    "final_result",
]
FRAMED = ["classify_user_intent", "frame_problem", "final_result"]
PROSE = ["classify_user_intent", "final_result"]

LEAD_SEQUENCES: dict[str, list[str]] = {
    "single": BUILD,
    "intersect": BUILD,
    "union": BUILD,
    "minus": BUILD,
    "orthologs": BUILD,
    "syntenic-orthologs": BUILD,
    "round-trip": BUILD,
    "go": BUILD,
    "combined": BUILD,
    "count-question": BUILD,
    "second-build": BUILD,
    "assent": BUILD,
    "controls-test": BUILD,
    "zero-then-relax": BUILD,
    "edit-param": EDIT,
    "add-step": EDIT,
    "replace-subtree": EDIT,
    "delete-step": EDIT,
    "delete-step-card": [
        "classify_user_intent",
        "get_live_strategy_state",
        "final_result",
    ],
    "clear": ["classify_user_intent", "clear_strategy", "final_result"],
    "proposal": ["classify_user_intent", "propose_changes", "final_result"],
    "sweep": [
        "classify_user_intent",
        "get_live_strategy_state",
        "build_control_set",
        *BUILD[1:-2],
        "optimize_search_parameters",
        "final_result",
    ],
    "consult": ["classify_user_intent", "consult_user", *BUILD[1:]],
    "no-search-states-it": FRAMED,
    "cross-organism": FRAMED,
    "portal-only": FRAMED,
    "other-site-experiment": BUILD,
    "frame-loop": FRAMED,
    "separation": [
        "classify_user_intent",
        "separate_controls",
        "adopt_separating_strategy",
        "verify_strategy",
        "final_result",
    ],
    "variants": ["classify_user_intent", "compare_search_variants", "final_result"],
    "save-gene-set": ["classify_user_intent", "save_gene_set", "final_result"],
    "export": [
        "classify_user_intent",
        "list_gene_sets",
        "export_gene_set",
        "final_result",
    ],
    "remember": ["classify_user_intent", "remember", "final_result"],
    "recall-preference": PROSE,
    "recap": ["read_ledger_section", "get_live_strategy_state", "final_result"],
    "gene-question": ["classify_user_intent", "read_gene_record", "final_result"],
    "attachment": ["classify_user_intent", "build_control_set", "final_result"],
    "eda-compare": [
        "classify_user_intent",
        "search_eda_studies",
        "describe_eda_study",
        "describe_eda_study",
        "open_eda_analysis",
        "set_eda_filters",
        "set_eda_filters",
        "preview_eda_subset",
        "run_eda_compute",
        "create_eda_step",
        "verify_strategy",
        "final_result",
    ],
    "eda-other-site": [
        "classify_user_intent",
        "search_eda_studies",
        "open_eda_analysis",
        "final_result",
    ],
    "off-topic": PROSE,
    "kinase-question": PROSE,
    "impact": PROSE,
    "context": PROSE,
    "rename": ["classify_user_intent", "rename_strategy", "final_result"],
    "echo": ["final_result"],
}


_REFUSED = {"open_eda_analysis": NOT_HERE}


def _attached(site_id: str) -> str:
    ids = SiteValues.for_site(site_id).controls.positive_ids[:2]
    return f"Use these.\nAttached gene-ID list from controls.csv: {', '.join(ids)}"


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("arc", sorted(LEAD_SEQUENCES))
def test_the_lead_plays_the_arc(arc: str, site_id: str) -> None:
    text = _attached(site_id) if arc == "attachment" else "Do it"
    refused = _REFUSED if arc == "eda-other-site" else {}

    calls = play("lead", site_id, f"{text} [[arc:{arc}]]", scene=Scene(refused=refused))

    assert names(calls) == LEAD_SEQUENCES[arc]


@pytest.mark.parametrize("site_id", SITES)
def test_an_attached_list_with_no_token_saves_a_control_set(site_id: str) -> None:
    calls = play("lead", site_id, _attached(site_id))

    assert names(calls) == ["classify_user_intent", "build_control_set", "final_result"]
    (saved,) = args_of(calls, "build_control_set")
    assert saved == {
        "name": "Controls from controls.csv",
        "positive_ids": SiteValues.for_site(site_id).controls.positive_ids[:2],
    }


def test_the_relax_turn_edits_the_strategy_the_first_turn_built() -> None:
    calls = play(
        "lead",
        "vectorbase",
        "Relax it [[arc:zero-then-relax]]",
        scene=Scene(instructions=framed_pins()),
    )

    assert names(calls) == EDIT


def test_a_build_on_a_framed_thread_extends_it() -> None:
    calls = play(
        "lead", "plasmodb", "[[arc:single]]", scene=Scene(instructions=framed_pins())
    )

    assert calls[0].args_as_dict()["intent"]["classification"] == "extend_strategy"


def test_a_withheld_build_ends_the_turn_on_the_edit_route() -> None:
    refusal = {"build_strategy": build_would_replace_the_strategy(1)}

    calls = play(
        "lead", "plasmodb", "[[arc:second-build]]", scene=Scene(refused=refusal)
    )

    assert names(calls) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "final_result",
    ]


@pytest.mark.parametrize("site_id", SITES)
def test_the_sweep_tunes_the_built_root_on_the_saved_controls(site_id: str) -> None:
    controls = SiteValues.for_site(site_id).controls

    calls = play("lead", site_id, "[[arc:sweep]]")

    (saved,) = args_of(calls, "build_control_set")
    assert saved["positive_ids"] == controls.positive_ids
    assert saved["negative_ids"] == controls.negative_ids
    (sweep,) = args_of(calls, "optimize_search_parameters")
    assert sweep["wdk_step_id"] == BUILT_ROOT_WDK_ID
    assert sweep["control_set_id"] == CONTROL_SET_ID


def test_the_sweep_on_a_built_thread_tunes_the_root_the_live_read_names() -> None:
    calls = play("lead", "plasmodb", "[[arc:sweep]]", scene=built_thread())

    assert names(calls) == [
        "classify_user_intent",
        "get_live_strategy_state",
        "build_control_set",
        "optimize_search_parameters",
        "final_result",
    ]
    (sweep,) = args_of(calls, "optimize_search_parameters")
    assert (sweep["wdk_step_id"], sweep["control_set_id"]) == (
        LIVE_ROOT_WDK_ID,
        CONTROL_SET_ID,
    )
    assert not calls[-1].args_as_dict()["strategyChanged"]


@pytest.mark.parametrize(
    "arc", ["orthologs", "syntenic-orthologs", "round-trip", "delete-step"]
)
def test_an_arc_on_a_framed_thread_edits_the_strategy(arc: str) -> None:
    calls = play(
        "lead", "plasmodb", f"[[arc:{arc}]]", scene=Scene(instructions=framed_pins())
    )

    assert names(calls) == EDIT


def test_the_portal_route_on_a_framed_thread_is_an_edit_that_builds_nothing() -> None:
    calls = play(
        "lead",
        "plasmodb",
        "[[arc:portal-only]]",
        scene=Scene(instructions=framed_pins()),
    )

    assert names(calls) == ["classify_user_intent", "edit_strategy", "final_result"]
    assert not calls[-1].args_as_dict()["strategyChanged"]


def test_a_build_reply_states_the_count_the_site_answers_now() -> None:
    calls = play("lead", "vectorbase", "[[arc:intersect]]")

    assert (
        calls[-1]
        .args_as_dict()["prose"]
        .endswith(f"The strategy returns {LIVE_ROOT_COUNT:,} genes.")
    )
    assert calls[-1].args_as_dict()["nextState"] == "complete"


def test_the_count_question_is_answered_by_the_recap() -> None:
    calls = play("lead", "plasmodb", f"{COUNT_QUESTION} [[arc:recap]]")

    prose = str(calls[-1].args_as_dict()["prose"])
    assert (
        prose.rsplit("\n\n", maxsplit=1)[-1]
        == f"The strategy returns {LIVE_ROOT_COUNT:,} genes."
    )


def test_the_product_clear_message_routes_to_the_clear_arc() -> None:
    calls = play("lead", "plasmodb", CLEAR_MESSAGE)

    assert names(calls) == ["classify_user_intent", "clear_strategy", "final_result"]
    assert calls[-1].args_as_dict()["prose"] == "The current strategy has been cleared."


def test_the_gene_set_takes_the_name_the_message_gives() -> None:
    text = "Save the genes of this strategy as a gene set named UAT G1. [[arc:save-gene-set]]"

    calls = play("lead", "vectorbase", text)

    assert args_of(calls, "save_gene_set") == [{"name": "UAT G1"}]


def test_the_rename_calls_the_tool_with_the_name_after_to() -> None:
    text = "Rename this strategy to UAT signal peptide screen. [[arc:rename]]"

    calls = play("lead", "plasmodb", text)

    assert args_of(calls, "rename_strategy") == [{"name": "UAT signal peptide screen"}]
    assert calls[-1].args_as_dict()["prose"] == (
        "Renamed the strategy to UAT signal peptide screen. "
        f"It returns {LIVE_ROOT_COUNT:,} genes."
    )
    assert not calls[-1].args_as_dict()["strategyChanged"]


def test_a_refused_rename_says_nothing_was_renamed() -> None:
    text = "Rename this strategy to UAT G2. [[arc:rename]]"
    refused = {"rename_strategy": "This conversation holds no strategy to rename."}

    calls = play("lead", "plasmodb", text, scene=Scene(refused=refused))

    assert names(calls) == ["classify_user_intent", "rename_strategy", "final_result"]
    assert calls[-1].args_as_dict()["prose"] == (
        "Nothing was renamed: this conversation holds no strategy yet."
    )


def test_pasted_controls_reach_the_sweep_and_the_separation() -> None:
    text = (
        "Separate these [[arc:separation]]\n"
        "Positive controls: AGAP000046 AGAP000128\n"
        "Negative controls: AGAP000427"
    )

    calls = play("lead", "vectorbase", text)

    (run,) = args_of(calls, "separate_controls")
    assert run["positive_controls"] == ["AGAP000046", "AGAP000128"]
    assert run["negative_controls"] == ["AGAP000427"]


def test_the_comparison_without_a_step_exports_nothing() -> None:
    text = (
        "Compare two groups. Do not make a strategy step. [[arc:eda-compare-no-step]]"
    )

    calls = play("lead", "plasmodb", text)

    assert names(calls) == [
        "classify_user_intent",
        "search_eda_studies",
        "describe_eda_study",
        "describe_eda_study",
        "open_eda_analysis",
        "set_eda_filters",
        "set_eda_filters",
        "preview_eda_subset",
        "run_eda_compute",
        "final_result",
    ]


def test_the_words_of_the_message_choose_no_ending() -> None:
    text = "Compare two groups. Do not make a strategy step. [[arc:eda-compare]]"

    calls = play("lead", "plasmodb", text)

    assert names(calls)[-3:] == ["create_eda_step", "verify_strategy", "final_result"]


def test_the_export_takes_the_id_the_listing_gave() -> None:
    calls = play("lead", "vectorbase", "[[arc:export]]")

    assert args_of(calls, "export_gene_set") == [
        {"gene_set_id": GENE_SET_ID, "output_format": "csv"}
    ]


def test_the_stored_preference_is_the_message_word_for_word() -> None:
    stated = "I prefer the Su et al. strand-specific dataset for gametocytes."

    calls = play("lead", "plasmodb", f"{stated} [[arc:remember]]")

    (stored,) = args_of(calls, "remember")
    assert stored["summary"] == stated
    assert stored["content"] == {"statement": stated}


def test_the_recalled_preference_is_the_reply() -> None:
    pins = memory_pins(
        "I prefer the Su et al. strand-specific dataset for gametocytes."
    )

    calls = play(
        "lead", "plasmodb", "[[arc:recall-preference]]", scene=Scene(instructions=pins)
    )

    assert calls[-1].args_as_dict()["prose"] == (
        "I prefer the Su et al. strand-specific dataset for gametocytes."
    )


def test_the_gene_question_reads_a_control_gene_of_the_site() -> None:
    gene = SiteValues.for_site("vectorbase").controls.positive_ids[0]

    calls = play("lead", "vectorbase", "[[arc:gene-question]]")

    assert args_of(calls, "read_gene_record") == [{"gene_id": gene}]
    assert calls[-1].args_as_dict()["prose"] == f"{gene} encodes a conserved protein."


def test_the_separation_measures_the_site_controls() -> None:
    controls = SiteValues.for_site("vectorbase").controls

    calls = play("lead", "vectorbase", "[[arc:separation]]")

    (run,) = args_of(calls, "separate_controls")
    assert run["positive_controls"] == controls.positive_ids
    assert run["negative_controls"] == controls.negative_ids
    assert args_of(calls, "adopt_separating_strategy")[0]["task_id"] == "task-1"


def test_the_eda_comparison_compares_the_two_sheet_groups() -> None:
    calls = play("lead", "plasmodb", "[[arc:eda-compare]]")

    (compute,) = args_of(calls, "run_eda_compute")
    assert compute["comparator_variable"] == {
        "entityId": "sample",
        "variableId": "genotype",
    }
    assert compute["group_a_labels"] == ["wildtype"]
    assert compute["group_b_labels"] == ["delta mutant"]
    assert compute["value_variable"] == {
        "entityId": "counts",
        "variableId": "SEQUENCE_READ_COUNT_SENSE",
    }


def test_the_study_another_site_publishes_is_declined_with_its_sentence() -> None:
    calls = play(
        "lead", "plasmodb", "[[arc:eda-other-site]]", scene=Scene(refused=_REFUSED)
    )

    assert args_of(calls, "open_eda_analysis")[0]["dataset_id"] == "DS_there"
    assert calls[-1].args_as_dict()["prose"] == NOT_HERE


def test_a_separation_that_did_not_run_offers_nothing() -> None:
    refusal = {"separate_controls": "No durable worker runs this turn."}

    calls = play("lead", "plasmodb", "[[arc:separation]]", scene=Scene(refused=refusal))

    assert names(calls) == [
        "classify_user_intent",
        "separate_controls",
        "final_result",
    ]
    assert not calls[-1].args_as_dict()["strategyChanged"]


def _intersect_thread() -> Scene:
    """A thread whose live read names a signal peptide step, a transmembrane
    step and the INTERSECT over them."""
    return Scene(
        answers={
            "get_live_strategy_state": {
                "steps": [
                    {"stepId": "step_sp", "searchName": "GenesWithSignalPeptide"},
                    {"stepId": "step_tm", "searchName": "GenesByTransmembraneDomains"},
                    {"stepId": "step_and", "searchName": None, "isRoot": True},
                ],
            }
        },
    )


def test_the_delete_card_removes_the_transmembrane_step_the_live_read_names() -> None:
    calls = play(
        "lead", "plasmodb", "[[arc:delete-step-card]]", scene=_intersect_thread()
    )

    assert names(calls) == [
        "classify_user_intent",
        "get_live_strategy_state",
        "delete_step",
        "final_result",
    ]
    (deleted,) = args_of(calls, "delete_step")
    assert deleted["step_id"] == "step_tm"
    assert len(str(deleted["reply"])) >= 20
    assert calls[-1].args_as_dict()["prose"] == DELETED_PROSE
    assert calls[-1].args_as_dict()["strategyChanged"] is True
