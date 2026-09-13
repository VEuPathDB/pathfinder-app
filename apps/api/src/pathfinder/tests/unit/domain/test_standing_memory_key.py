"""The key a standing memory is written under, derived from its own name."""

from __future__ import annotations

import pytest

from pathfinder.domain.memory import (
    MAX_STANDING_KEY_LENGTH,
    UnnamedMemoryError,
    standing_memory_key,
)


def test_one_name_however_it_is_written_is_one_key() -> None:
    assert standing_memory_key("Default organism") == "default-organism"
    assert standing_memory_key("  default   organism  ") == "default-organism"


def test_two_names_that_share_no_word_do_not_share_a_key() -> None:
    assert standing_memory_key("Default organism") != standing_memory_key(
        "Default record type"
    )


def test_a_long_name_is_cut_to_a_key_the_store_can_index() -> None:
    """The key is half of a primary key, and a btree row has a size limit."""
    key = standing_memory_key("organism " * 60)

    assert len(key) <= MAX_STANDING_KEY_LENGTH
    assert not key.endswith("-")


def test_a_name_with_no_letter_or_digit_is_refused() -> None:
    """Two such names would share one bucket and overwrite each other."""
    with pytest.raises(UnnamedMemoryError, match=r"\?\?\?"):
        standing_memory_key("???")

    with pytest.raises(UnnamedMemoryError):
        standing_memory_key("---")
