"""An expression too long to describe reads by the join its clauses use."""

from __future__ import annotations

from itertools import product
from string import ascii_lowercase

from veupathdb.domain.parameters import PhyleticTree

from pathfinder.domain.strategy.expression_handles import (
    READING_LIMIT,
    expression_reading,
)


def _codes(count: int) -> list[str]:
    return ["".join(letters) for letters in product(ascii_lowercase, repeat=3)][:count]


def test_an_and_of_many_clauses_reads_as_and_clauses() -> None:
    text = " AND ".join(f"{code}>=1T" for code in _codes(300))
    assert len(text) > READING_LIMIT

    assert expression_reading(text, PhyleticTree()) == (
        f"names 300 codes in 300 AND clauses, {len(text):,} characters"
    )


def test_an_or_of_terms_reads_as_or_terms() -> None:
    codes = _codes(300)
    text = " OR ".join(
        f"{first}>=1T AND {second}=0T"
        for first, second in zip(codes[::2], codes[1::2], strict=True)
    )
    assert len(text) > READING_LIMIT

    assert expression_reading(text, PhyleticTree()) == (
        f"names 300 codes in 150 OR terms, {len(text):,} characters"
    )
