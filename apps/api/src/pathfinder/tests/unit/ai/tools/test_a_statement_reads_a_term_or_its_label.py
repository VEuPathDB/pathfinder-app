"""A parameter states a word by the option whose label carries it, whether the
call names that option by its term or by its label."""

from __future__ import annotations

from veupathdb.wdk import WDKSearch

from pathfinder.ai.tools.standalone._qualifier_words import statements, stem


def _gene_type() -> WDKSearch:
    """Gene Type, with the Include Pseudogenes terms that differ from their labels."""
    return WDKSearch.model_validate(
        {
            "urlSegment": "GenesByGeneType",
            "displayName": "Gene Type",
            "parameters": [
                {
                    "name": "includePseudogenes",
                    "displayName": "Include",
                    "type": "single-pick-vocabulary",
                    "displayType": "select",
                    "isVisible": True,
                    "vocabulary": [
                        ["N", "no", None],
                        ["Y", "Yes, with pseudogenes", None],
                        ["P", "Pseudogenes only", None],
                    ],
                },
            ],
        }
    )


def test_a_term_and_its_label_both_state_the_word() -> None:
    (statement,) = statements(_gene_type(), stem("pseudogenes"))

    assert [
        statement.states(value)
        for value in ("Y", "Yes, with pseudogenes", "P", "Pseudogenes only", "N", "no")
    ] == [True, True, True, True, False, False]
    assert statement.allowed == ("Yes, with pseudogenes", "Pseudogenes only")


def test_a_parameter_named_by_the_word_is_switched_off_by_term_or_label() -> None:
    search = WDKSearch.model_validate(
        {
            "urlSegment": "GenesByPseudogeneFlag",
            "parameters": [
                {
                    "name": "pseudo",
                    "displayName": "Pseudogenes",
                    "type": "single-pick-vocabulary",
                    "displayType": "select",
                    "isVisible": True,
                    "vocabulary": [["0", "no", None], ["1", "yes", None]],
                },
            ],
        }
    )

    (statement,) = statements(search, stem("pseudogenes"))

    assert [statement.states(v) for v in ("0", "no", "1", "yes")] == [
        False,
        False,
        True,
        True,
    ]
