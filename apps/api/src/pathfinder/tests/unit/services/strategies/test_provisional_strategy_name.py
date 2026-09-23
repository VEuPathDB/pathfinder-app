"""A strategy pushed before its thread has a title is named after the request.

The rule is the one the web applies to an untitled thread in the sidebar.
"""

from __future__ import annotations

import pytest
from assistant_core.persistence.repositories.conversation import (
    DEFAULT_CONVERSATION_NAME,
)

from pathfinder.services.strategies.naming import provisional_strategy_name


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        (
            (
                "  Find genes upregulated in the Anopheles midgut 24 hours after a "
                "blood meal versus sugar fed  "
            ),
            "Find genes upregulated in the Anopheles midgut 24 hours...",
        ),
        ("x" * 70, "x" * 60 + "..."),
    ],
)
def test_a_long_request_is_cut_on_a_word_with_an_ellipsis(
    prompt: str, expected: str
) -> None:
    assert provisional_strategy_name(prompt) == expected


def test_a_short_request_is_the_name_with_its_spaces_collapsed() -> None:
    assert (
        provisional_strategy_name("find kinases\n in P. falciparum")
        == "find kinases in P. falciparum"
    )


@pytest.mark.parametrize("prompt", ["", "  \n "])
def test_no_request_leaves_the_placeholder(prompt: str) -> None:
    assert provisional_strategy_name(prompt) == DEFAULT_CONVERSATION_NAME
