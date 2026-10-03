"""The cases recorded from the dry UAT: one per investigation, every turn as
driven unless the curator note names the one restated."""

from __future__ import annotations

import datetime

import pytest

from pathfinder.evals.case import EvalCase, GateAnswer, GatePlan, RecordedCount
from pathfinder.evals.store import load_corpus

_LEAVE = GatePlan(policy="leave")


def _yes(card: str, turn: int) -> GateAnswer:
    return GateAnswer(card=card, turn=turn)


def _picks(turn: int, *picks: str) -> GateAnswer:
    return GateAnswer(card="consult_user", turn=turn, picks=list(picks))


_DRY = [case for case in load_corpus() if case.name.startswith("uat-dry-")]
_BY_NAME = {case.name: case for case in _DRY}


def _count(count: int) -> RecordedCount:
    return RecordedCount(
        count=count, build="71", measured_on=datetime.date(2026, 9, 28)
    )


def test_every_investigation_of_the_dry_uat_is_one_case() -> None:
    assert sorted(_BY_NAME) == [
        "uat-dry-a-cryptodb",
        "uat-dry-a-piroplasmadb",
        "uat-dry-a-plasmodb",
        "uat-dry-a-toxodb",
        "uat-dry-b-fungidb",
        "uat-dry-b-giardiadb",
        "uat-dry-b-tritrypdb",
        "uat-dry-c-piroplasmadb",
        "uat-dry-c-plasmodb",
        "uat-dry-d-amoebadb",
        "uat-dry-d-vectorbase",
        "uat-dry-d-veupathdb",
    ]


@pytest.mark.parametrize("case", _DRY, ids=[case.name for case in _DRY])
def test_a_dry_case_holds_the_unit_and_no_unstated_value(case: EvalCase) -> None:
    expected = case.expected
    # A dry case builds and counts in genes, or it ends on the card the design
    # asks for and counts nothing.
    assert (expected.builds_strategy, expected.ends_on, expected.counts_in_genes) in {
        (True, "none", True),
        (False, "consult", None),
    }
    assert (
        expected.assumed_stated,
        case.effort,
        case.provenance.origin,
        case.provenance.reference.startswith("uat/flows-dry-uat.md#u"),
        case.assert_de_identified(),
    ) == (0, "medium", "uat-flow", True, True)


def test_the_toxodb_case_leaves_no_gap_for_the_withdrawn_cutoff() -> None:
    case = _BY_NAME["uat-dry-a-toxodb"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (
        5,
        GatePlan(policy="leave", answers=[_yes("delete_step", 3)]),
    )
    assert (
        expected.structure,
        expected.parameters,
        expected.unexpressed_requirements,
        expected.reply_mentions,
        expected.root_count,
    ) == (
        "(GenesWithSignalPeptide INTERSECT GenesByTransmembraneDomains)",
        {"GenesByTransmembraneDomains": {"min_tm": "0", "max_tm": "0"}},
        0,
        ["ME49 signal peptide, no transmembrane domain"],
        _count(461),
    )


def test_the_cryptodb_case_links_the_workspace_route() -> None:
    case = _BY_NAME["uat-dry-a-cryptodb"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (6, _LEAVE)
    assert (
        expected.reply_mentions,
        expected.reply_omits,
        expected.turn_reply_mentions,
        expected.parameters,
        expected.root_count,
    ) == (
        ["/app/workspace/strategies/"],
        ["/app/strategy/"],
        {2: ["497"], 3: ["497"]},
        {
            "GenesByOrthologPattern": {
                "included_species": "tgon",
                "excluded_species": "hsap",
            }
        },
        _count(68),
    )


def test_the_piroplasmadb_case_states_both_counts_whichever_tree_keeps_them() -> None:
    """The count question that keeps the list is answered by an offered step."""
    case = _BY_NAME["uat-dry-a-piroplasmadb"]
    expected = case.expected

    assert (len(case.turns), case.gates, expected.ends_on) == (
        5,
        GatePlan(
            policy="leave",
            answers=[
                _yes("propose_changes", 2),
                _yes("propose_changes", 3),
                _yes("propose_changes", 4),
            ],
        ),
        "none",
    )
    assert (
        expected.structure,
        expected.step_count,
        expected.parameters,
        expected.turn_reply_mentions,
        expected.reply_mentions,
        expected.root_count,
    ) == (
        None,
        None,
        {},
        {},
        [],
        None,
    )


def test_the_tritrypdb_case_names_the_floor_by_its_label() -> None:
    case = _BY_NAME["uat-dry-b-tritrypdb"]
    expected = case.expected
    rnaseq = "GenesByRNASeqtbruTREU927_Naguleswaran_procyclic_ebi_rnaSeq_RSRC"

    assert (len(case.turns), case.gates) == (6, _LEAVE)
    assert (
        expected.turn_reply_mentions,
        expected.turn_reply_omits,
        expected.parameters,
        expected.step_count,
        expected.root_count,
    ) == (
        {},
        {1: ["734.0197714535435"], 3: [rnaseq, "GenesByGoTerm"]},
        {},
        None,
        None,
    )


def test_the_giardiadb_case_pins_the_shape_and_not_the_field_choice() -> None:
    case = _BY_NAME["uat-dry-b-giardiadb"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (5, _LEAVE)
    assert (
        expected.structure,
        expected.root_operator,
        expected.turn_reply_mentions,
        expected.reply_mentions,
        expected.root_count,
    ) == (None, None, {}, [], None)


def test_the_fungidb_case_answers_five_cards_and_shows_the_term_label() -> None:
    """The obsolete term binds because the last message says to use it."""
    case = _BY_NAME["uat-dry-b-fungidb"]
    expected = case.expected

    assert case.turns[4].endswith(
        "If the only fitting term is marked obsolete, use it anyway and say so."
    )
    assert (len(case.turns), case.gates.policy, case.gates.answers) == (
        5,
        "leave",
        [
            _yes("propose_changes", 1),
            _picks(1, "Use a direct protein-prediction search if available"),
            _yes("propose_changes", 1),
            _picks(1, "Keep the current GPI-biosynthesis search"),
            _yes("delete_step", 2),
        ],
    )
    assert (
        expected.parameters,
        expected.reply_mentions,
        expected.root_count,
    ) == (
        {"GenesByGoTerm": {"go_typeahead": "GO:0031225"}},
        ["GO:0031225", "obsolete anchored component of membrane"],
        _count(58),
    )


def test_the_plasmodb_case_summarises_the_set_this_conversation_saved() -> None:
    case = _BY_NAME["uat-dry-c-plasmodb"]
    expected = case.expected

    assert (len(case.turns), case.gates, case.turns[8][-27:]) == (
        12,
        GatePlan(policy="leave", answers=[_yes("delete_step", 10)]),
        "'vaccine candidates draft'.",
    )
    assert (
        case.turns[0][-63:],
        expected.reply_mentions,
        expected.unexpressed_requirements,
        expected.turn_reply_mentions,
        expected.turn_reply_omits,
        expected.root_count,
    ) == (
        "or at least one transmembrane domain, expressed in sporozoites.",
        ["vaccine candidates draft", "288"],
        0,
        {5: ["884"]},
        {9: ["step_"]},
        _count(288),
    )


def test_the_vectorbase_case_leaves_no_gap_for_the_settled_question() -> None:
    case = _BY_NAME["uat-dry-d-vectorbase"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (4, _LEAVE)
    assert (
        expected.root_operator,
        expected.unexpressed_requirements,
        expected.step_count,
        expected.root_count,
    ) == ("MINUS", 0, 5, _count(12))


def test_the_amoebadb_case_builds_the_definition_the_message_states() -> None:
    case = _BY_NAME["uat-dry-d-amoebadb"]
    expected = case.expected

    assert (len(case.turns), case.gates, case.turns[1][-82:]) == (
        4,
        GatePlan(policy="leave", answers=[_yes("delete_step", 2)]),
        "(minimum expression percentile 1), if AmoebaDB has an expression dataset for that?",
    )
    assert (
        expected.turn_reply_mentions,
        expected.reply_mentions,
        expected.root_count,
    ) == ({1: ["17"]}, ["17", "68"], _count(68))


def test_the_portal_case_takes_the_genus_and_names_no_internal_search() -> None:
    case = _BY_NAME["uat-dry-d-veupathdb"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (4, _LEAVE)
    assert (
        expected.structure,
        expected.turn_reply_mentions,
        expected.turn_reply_omits,
        expected.reply_mentions,
        expected.parameters["GenesByOrthologs"],
        expected.root_count,
    ) == (
        "GenesByOrthologs(GenesByGoTerm)",
        {0: ["429"]},
        {2: ["GenesByGoTerm"]},
        ["PVP01_0005540"],
        {"organism": "Plasmodium falciparum 3D7"},
        _count(7),
    )


def _measured(count: int) -> RecordedCount:
    return RecordedCount(
        count=count, build="71", measured_on=datetime.date(2026, 9, 30)
    )


def test_the_knowlesi_case_holds_no_records_gap_and_the_stated_exclusion() -> None:
    case = _BY_NAME["uat-dry-a-plasmodb"]
    expected = case.expected

    assert (len(case.turns), case.gates) == (1, _LEAVE)
    assert (
        expected.builds_strategy,
        expected.ends_on,
        expected.structure,
        expected.parameters,
        expected.unmet_requirements,
        expected.reply_mentions,
        expected.root_count,
    ) == (False, "consult", None, {}, None, [], None)


_GPI_ANSWER = (
    "Use a text search for GPI anchor in the gene product descriptions as the "
    "stand-in and keep it OR with the signal peptide"
)


def test_the_winnie_case_holds_no_organism_gap_on_unclear_records() -> None:
    case = _BY_NAME["uat-dry-c-piroplasmadb"]
    expected = case.expected

    assert (len(case.turns), case.gates.answers) == (
        1,
        [_picks(0, "Specify an alternative evidence type"), _picks(0, _GPI_ANSWER)],
    )
    assert (
        expected.structure,
        expected.unmet_requirements,
        expected.reply_mentions,
        expected.root_count,
    ) == (None, 0, [], None)
