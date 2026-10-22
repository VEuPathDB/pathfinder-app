"""The OrthoMCL cases load, are de-identified, and state writings the scorer reads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from veupathdb.domain.parameters import PhyleticExpression, PhyleticTree, TaxonEntry

from pathfinder.evals.case import EvalCase, ExpectedOutcome
from pathfinder.evals.distance import ComparisonNode
from pathfinder.evals.scoring import ObservedOutcome, canonical_structure, score_case
from pathfinder.evals.store import CORPUS_DIR

_FILES = sorted(CORPUS_DIR.glob("orthomcl-*.json"))
_CASES = {path.stem: EvalCase.model_validate_json(path.read_text()) for path in _FILES}


def test_the_corpus_holds_the_19_measured_cases() -> None:
    assert len(_CASES) == 19
    assert {case.site_id for case in _CASES.values()} == {"orthomcl"}


@pytest.mark.parametrize("name", sorted(_CASES))
def test_each_case_is_de_identified_and_states_a_readable_shape(name: str) -> None:
    case = _CASES[name]

    assert case.assert_de_identified()
    if case.expected.structure is not None:
        assert canonical_structure(case.expected.structure)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_every_accepted_writing_parses(name: str) -> None:
    for writings in _CASES[name].expected.expressions.values():
        for writing in writings:
            assert PhyleticExpression.parse(writing).site_reading().codes()


def test_the_measured_counts_and_card_checks_are_pinned() -> None:
    def count(name: str) -> int | None:
        recorded = _CASES[name].expected.root_count
        return None if recorded is None else recorded.count

    asks = _CASES["orthomcl-all-plasmodium-asks-which-all"].expected
    offers = _CASES["orthomcl-expanded-families-question-offers-readings"].expected

    assert (
        count("orthomcl-in-3d7-missing-from-two-falciparum-strains"),
        count("orthomcl-more-proteins-in-one-genome-than-another"),
        count("orthomcl-one-protein-in-each-cryptosporidium-genome"),
    ) == (304, 3896, 1736)
    assert (asks.consult_options_min, asks.consult_option_mentions) == (
        3,
        ["61", "55", "23"],
    )
    assert offers.consult_options_min == 2
    assert _CASES[
        "orthomcl-singletons-counted-by-organism"
    ].expected.reply_mentions == ["Brachionus plicatilis"]


def test_no_curator_note_is_a_draft() -> None:
    assert [n for n, c in _CASES.items() if "Draft" in c.provenance.curator_note] == []


def test_the_falciparum_strain_case_accepts_only_the_sum_of_products() -> None:
    writings = _CASES[
        "orthomcl-in-3d7-missing-from-two-falciparum-strains"
    ].expected.expressions["GroupsByPhyleticPattern"]

    assert len(writings) == 1
    assert writings[0].count(" OR ") == 1


def test_the_bands_reply_states_clade_totals_in_either_wording() -> None:
    case = _CASES["orthomcl-expanded-in-toxoplasma-over-plasmodium-in-bands"]

    assert case.expected.turn_reply_mentions == {1: ["total | average"]}


def test_a_protein_ceiling_at_zero_fails_the_absence_the_share_case_states() -> None:
    case = _CASES["orthomcl-most-plasmodium-genomes-no-toxoplasma"]
    (accepted,) = case.expected.expressions["GroupsByPhyleticPattern"]
    codes = PhyleticExpression.parse(accepted).codes()
    taxonomy = PhyleticTree.from_taxa(
        [
            TaxonEntry(id=code, parent_id=None, code=code, label=code, clade=False)
            for code in codes
        ]
    )

    def graded(expression: str) -> list[str]:
        observed = ObservedOutcome(
            built_strategy=True,
            tree=ComparisonNode(
                search_name="GroupsByPhyleticPattern",
                parameters={"phyletic_expression": expression},
            ),
        )
        score = score_case(case, observed, taxonomy)
        return [d.field for d in score.differences if d.field.startswith("expr")]

    assert graded(accepted) == []
    for ceiling in ("<=0", "<1", "<=0T"):
        assert graded(accepted.replace("=0T", ceiling)) == [
            "expressions.GroupsByPhyleticPattern"
        ]


def test_a_writing_the_grammar_refuses_is_refused_by_the_case() -> None:
    with pytest.raises(ValidationError, match="expressions"):
        ExpectedOutcome(
            builds_strategy=True,
            expressions={"GroupsByPhyleticPattern": ["APIC=139T AND"]},
        )
