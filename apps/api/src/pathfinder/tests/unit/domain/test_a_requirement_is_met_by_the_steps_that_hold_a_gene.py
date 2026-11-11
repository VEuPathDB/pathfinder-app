from __future__ import annotations

import pytest
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode

from pathfinder.domain.step_membership import (
    Holding,
    StepFact,
    implied_holdings,
    requirement_by_steps,
)


def _leaf(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=f"Search_{step_id}")


def _join(
    step_id: str, op: CombineOp, left: StrategyStepNode, right: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=COMBINE_SEARCH_NAME,
        operator=op,
        primary_input=left,
        secondary_input=right,
    )


def _facts(**held: Holding) -> dict[str, StepFact]:
    return {step: StepFact(title=step, holding=h) for step, h in held.items()}


_NESTED = _join(
    "root",
    CombineOp.MINUS,
    _leaf("a"),
    _join("bc", CombineOp.MINUS, _leaf("b"), _leaf("c")),
)


@pytest.mark.parametrize(
    ("b", "c", "fits"),
    [("in", "out", "no"), ("out", "out", "yes"), ("in", "in", "yes")],
)
def test_a_subtracted_minus_holds_a_gene_its_own_minus_removes(
    b: Holding, c: Holding, fits: str
) -> None:
    found = requirement_by_steps(
        _NESTED, "not b unless c", frozenset({"b", "c"}), _facts(b=b, c=c)
    )

    assert found.fits == fits


def test_a_right_minus_subtracts_its_primary_input() -> None:
    root = _join("root", CombineOp.RMINUS, _leaf("a"), _leaf("b"))

    found = requirement_by_steps(root, "not a", frozenset({"a"}), _facts(a="in"))

    assert (found.fits, [f.sentence for f in found.facts]) == (
        "no",
        ["In the step 'a', which the strategy subtracts"],
    )


def test_a_transform_ends_the_steps_membership_reads() -> None:
    transformed = StrategyStepNode(
        id="t", search_name="GenesByOrthologs", primary_input=_leaf("a")
    )
    root = _join("root", CombineOp.INTERSECT, transformed, _leaf("b"))

    assert implied_holdings(root) == {"t": "in", "b": "in"}


def test_a_root_gene_is_in_what_it_intersects_and_out_of_what_it_subtracts() -> None:
    root = _join(
        "root",
        CombineOp.INTERSECT,
        _join("u", CombineOp.UNION, _leaf("e1"), _leaf("e2")),
        _join(
            "m",
            CombineOp.MINUS,
            _leaf("kept"),
            _join("x", CombineOp.UNION, _leaf("x1"), _leaf("x2")),
        ),
    )

    assert implied_holdings(root) == {
        "e1": None,
        "e2": None,
        "kept": "in",
        "x1": "out",
        "x2": "out",
    }


def test_a_requirement_no_reachable_step_states_is_refused() -> None:
    with pytest.raises(ValueError, match="no step the root reaches"):
        requirement_by_steps(_leaf("a"), "kinase", frozenset({"z"}), _facts(a="in"))
