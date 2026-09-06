"""Tests for the strategy revision fingerprint.

The fingerprint must change on parameter and topology edits, and stay the same
on count refreshes.
"""

from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.domain.strategy.validation import StepValidation

from pathfinder.domain.strategy.revision import strategy_revision


def _leaf(fold_change: str = "1", step_id: str = "step_a") -> StrategyStepNode:
    return StrategyStepNode.model_validate(
        {
            "id": step_id,
            "searchName": "GenesByRNASeqEvidence",
            "parameters": {
                "fold_change": {"type": "string", "value": fold_change},
                "organism": {"type": "string", "value": "Plasmodium falciparum 3D7"},
            },
        },
    )


def _ast(root: StrategyStepNode, **extra: object) -> StrategyAst:
    return StrategyAst.model_validate(
        {"recordType": "transcript", "root": root.model_dump(by_alias=True), **extra},
    )


def test_no_strategy_has_no_revision() -> None:
    assert strategy_revision(None) == ""


def test_revision_is_stable_for_the_same_strategy() -> None:
    assert strategy_revision(_ast(_leaf())) == strategy_revision(_ast(_leaf()))


def test_editing_a_parameter_changes_the_revision() -> None:
    """A parameter edit changes the gene set, so it must change the fingerprint."""
    assert strategy_revision(_ast(_leaf("1"))) != strategy_revision(_ast(_leaf("2")))


def test_changing_the_search_changes_the_revision() -> None:
    other = _leaf().model_copy(update={"search_name": "GenesByTaxon"})
    assert strategy_revision(_ast(_leaf())) != strategy_revision(_ast(other))


def test_refreshed_counts_do_not_change_the_revision() -> None:
    """Counts are observations of the strategy, not the strategy."""
    before = _ast(_leaf(), stepCounts={"step_a": 2862})
    after = _ast(_leaf(), stepCounts={"step_a": 587})
    assert strategy_revision(before) == strategy_revision(after)


def test_wdk_step_ids_and_validations_do_not_change_the_revision() -> None:
    before = _ast(_leaf())
    after = _ast(
        _leaf(),
        wdkStepIds={"step_a": 4242},
        stepValidations={
            "step_a": StepValidation(level="NONE", is_valid=False).model_dump(
                by_alias=True
            )
        },
    )
    assert strategy_revision(before) == strategy_revision(after)


def test_renaming_does_not_change_the_revision() -> None:
    before = _ast(_leaf(), name="Draft", description="first pass")
    after = _ast(_leaf(), name="Final", description="ready for the paper")
    assert strategy_revision(before) == strategy_revision(after)


def test_display_name_does_not_change_the_revision() -> None:
    renamed = _leaf().model_copy(update={"display_name": "Upregulated in gametocytes"})
    assert strategy_revision(_ast(_leaf())) == strategy_revision(_ast(renamed))


def test_adding_a_step_changes_the_revision() -> None:
    combined = StrategyStepNode.model_validate(
        {
            "id": "step_c",
            "searchName": "__combine__",
            "operator": "INTERSECT",
            "primaryInput": _leaf(step_id="step_a").model_dump(by_alias=True),
            "secondaryInput": _leaf(step_id="step_b").model_dump(by_alias=True),
        },
    )
    assert strategy_revision(_ast(_leaf())) != strategy_revision(_ast(combined))


def test_changing_the_combine_operator_changes_the_revision() -> None:
    def _combined(operator: str) -> StrategyStepNode:
        return StrategyStepNode.model_validate(
            {
                "id": "step_c",
                "searchName": "__combine__",
                "operator": operator,
                "primaryInput": _leaf(step_id="step_a").model_dump(by_alias=True),
                "secondaryInput": _leaf(step_id="step_b").model_dump(by_alias=True),
            },
        )

    assert strategy_revision(_ast(_combined("INTERSECT"))) != strategy_revision(
        _ast(_combined("UNION")),
    )


def test_swapping_the_inputs_changes_the_revision() -> None:
    """INTERSECT is symmetric but MINUS is not, so input order is semantic."""

    def _minus(primary_fold: str, secondary_fold: str) -> StrategyStepNode:
        return StrategyStepNode.model_validate(
            {
                "id": "step_c",
                "searchName": "__combine__",
                "operator": "MINUS",
                "primaryInput": _leaf(primary_fold, "step_a").model_dump(by_alias=True),
                "secondaryInput": _leaf(secondary_fold, "step_b").model_dump(
                    by_alias=True,
                ),
            },
        )

    assert strategy_revision(_ast(_minus("1", "2"))) != strategy_revision(
        _ast(_minus("2", "1")),
    )


def test_regenerated_step_ids_do_not_change_the_revision() -> None:
    """A duplicated conversation re-keys steps without changing the science."""
    assert strategy_revision(_ast(_leaf(step_id="step_a"))) == strategy_revision(
        _ast(_leaf(step_id="step_zzz")),
    )


def test_a_step_added_but_not_yet_combined_moves_the_revision() -> None:
    """A second root is a real edit."""
    base = StrategyAst(record_type="transcript", root=_leaf(step_id="a"))
    with_detached = StrategyAst(
        record_type="transcript",
        root=_leaf(step_id="a"),
        detached_roots=[_leaf(step_id="b")],
    )

    assert strategy_revision(base) != strategy_revision(with_detached)


def test_detached_roots_are_order_independent_in_the_fingerprint() -> None:
    """Two roots have no meaningful order, so their order is not an edit."""
    one = StrategyAst(
        record_type="transcript",
        root=_leaf(step_id="a"),
        detached_roots=[_leaf(step_id="b"), _leaf(step_id="c")],
    )
    other = StrategyAst(
        record_type="transcript",
        root=_leaf(step_id="a"),
        detached_roots=[_leaf(step_id="c"), _leaf(step_id="b")],
    )

    assert strategy_revision(one) == strategy_revision(other)
