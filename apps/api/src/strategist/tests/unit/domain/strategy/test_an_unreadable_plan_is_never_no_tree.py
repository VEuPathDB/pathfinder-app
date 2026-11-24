from __future__ import annotations

from veupathdb import JSONObject

from strategist.domain.strategy.revision import (
    parse_strategy_ast,
    strategy_revision_of_raw,
)
from strategist.domain.unread import Unread

_UNREADABLE: JSONObject = {
    "recordType": "transcript",
    "root": {
        "id": "step_root",
        "searchName": "__combine__",
        "operator": "INTERSECT",
        "primaryInput": {"id": "step_a", "searchName": "GenesByText"},
        "secondaryInput": {"id": "step_a", "searchName": "GenesByText"},
    },
}


def test_a_stored_tree_that_does_not_validate_is_unread() -> None:
    parsed = parse_strategy_ast(_UNREADABLE)

    assert parsed == Unread(
        reason=(
            "root: Value error, combine step "
            "cannot use the same step on both inputs (stepId='step_a'); use a "
            "single leaf or combine with a different step"
        )
    )


def test_a_payload_with_no_tree_is_no_tree() -> None:
    assert (parse_strategy_ast({}), parse_strategy_ast({"recordType": "x"})) == (
        None,
        None,
    )


def test_an_unreadable_tree_has_a_revision_of_its_own() -> None:
    held = strategy_revision_of_raw(_UNREADABLE)
    moved = strategy_revision_of_raw({**_UNREADABLE, "recordType": "gene"})

    assert (len(held), held == "", held == moved) == (16, False, False)
