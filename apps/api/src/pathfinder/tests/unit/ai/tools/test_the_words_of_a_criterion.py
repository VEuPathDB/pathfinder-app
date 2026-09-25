"""A criterion's words are read by a light stem, and a negated word states an
absence, not a qualifier."""

from __future__ import annotations

import pytest

from pathfinder.ai.tools.standalone._qualifier_words import qualifiers_of, stem


@pytest.mark.parametrize(
    ("word", "read"),
    [
        ("pseudogenes", "pseudogen"),
        ("pseudogene", "pseudogen"),
        ("syntenic", "synten"),
        ("secreted", "secret"),
        ("mitochondrial", "mitochondri"),
        ("gene", "gene"),
    ],
)
def test_a_word_and_its_forms_read_alike(word: str, read: str) -> None:
    assert stem(word) == read


@pytest.mark.parametrize(
    "text",
    [
        "kinases, no pseudogenes",
        "kinases, not pseudogenes",
        "kinases without pseudogenes",
        "non-pseudogenes kinases",
    ],
)
def test_a_negated_word_is_no_qualifier(text: str) -> None:
    assert [q.word for q in qualifiers_of(text)] == ["kinases"]


def test_each_stem_is_read_once_in_text_order() -> None:
    assert [q.word for q in qualifiers_of("secreted kinases, secretion kinase")] == [
        "secreted",
        "kinases",
        "secretion",
    ]
