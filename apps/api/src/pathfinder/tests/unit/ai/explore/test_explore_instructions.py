from __future__ import annotations

import re

from pathfinder.ai.agents.vocabulary import USER_FACING_VOCABULARY
from pathfinder.ai.explore._explore_instructions import EXPLORE_INSTRUCTIONS
from pathfinder.ai.models.mock.site_values import SiteValues

GENE_ID_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z]?\d{3,}\b")
_GENE_SITES = (
    "amoebadb",
    "cryptodb",
    "fungidb",
    "giardiadb",
    "hostdb",
    "microsporidiadb",
    "piroplasmadb",
    "plasmodb",
    "toxodb",
    "trichdb",
    "tritrypdb",
    "vectorbase",
    "veupathdb",
)


def site_organism_genera() -> set[str]:
    return {
        organism.split()[0]
        for site in _GENE_SITES
        for organism in (
            SiteValues.for_site(site).organism,
            *SiteValues.for_site(site).portal_organisms,
        )
    }


def _missing(*words: str) -> list[str]:
    return [word for word in words if word not in EXPLORE_INSTRUCTIONS]


def test_explore_names_every_mode() -> None:
    named = ("Explore mode", "Build", "Auto", "consult_user", "propose_readings")

    assert _missing(*named) == []


def test_explore_leaves_one_proposal_to_the_build_button() -> None:
    assert _missing("With one proposal", "Build button") == []
    assert '"build it"' not in EXPLORE_INSTRUCTIONS


def test_explore_proposes_a_whole_plan_and_only_when_it_helps() -> None:
    named = (
        "A proposal is optional",
        "one proposal of two searches",
        "Never offer the parts of one plan as alternatives",
        "more than one way, propose each way as an alternative",
    )

    assert _missing(*named) == []


def test_explore_marks_a_hypothesis() -> None:
    assert _missing("hypothesis", "cite") == []


def test_explore_names_no_worked_example() -> None:
    genera = site_organism_genera()

    assert {"Plasmodium", "Toxoplasma", "Giardia"} <= genera
    assert GENE_ID_PATTERN.search("PF3D7_1133400 and TGME49_208030") is not None
    assert GENE_ID_PATTERN.search(EXPLORE_INSTRUCTIONS) is None
    assert sorted(name for name in genera if name in EXPLORE_INSTRUCTIONS) == []


def test_explore_carries_the_vocabulary_rule() -> None:
    tail = EXPLORE_INSTRUCTIONS[-len(USER_FACING_VOCABULARY) :]

    assert tail == USER_FACING_VOCABULARY


def test_explore_writes_ascii_only() -> None:
    assert EXPLORE_INSTRUCTIONS.isascii()


def test_explore_asks_before_it_reads_the_account() -> None:
    assert _missing("ask_to_read_the_account", "other Strategist conversations") == []


def test_a_question_about_the_account_is_answered_from_it() -> None:
    named = ("when the researcher asks about them", "Never say you cannot reach them")

    assert _missing(*named) == []


def test_explore_reads_a_genome_fact_from_the_record_that_carries_it() -> None:
    named = ("list_record_columns", "read_search_table", "BUSCO")

    assert _missing(*named) == []


def test_a_question_the_sites_answer_starts_from_the_site() -> None:
    named = (
        "starts from the site's catalog",
        "the literature then supports, explains or extends",
    )
    assert _missing(*named) == []
