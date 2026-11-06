"""A nested group of steps carries a name made from the steps inside it."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.domain.strategy.combine_naming import name_the_combines


def _leaf(step_id: str, name: str) -> StrategyStep:
    return StrategyStep(
        id=step_id, kind=StepKind.SEARCH, search_name="GenesByText", display_name=name
    )


def _combine(
    step_id: str,
    primary: str,
    secondary: str,
    operator: CombineOp = CombineOp.UNION,
    **fields: object,
) -> StrategyStep:
    return StrategyStep.model_validate(
        {
            "id": step_id,
            "kind": StepKind.COMBINE,
            "operator": operator,
            "primary_input_id": primary,
            "secondary_input_id": secondary,
            **fields,
        }
    )


def _named(*steps: StrategyStep) -> dict[str, StrategyStep]:
    by_id = {step.id: step for step in steps}
    name_the_combines(by_id)
    return by_id


def test_a_union_nested_on_the_secondary_side_is_named_by_its_steps() -> None:
    steps = _named(
        _leaf("taxon", "Genes by taxon"),
        _leaf("pexel", "PEXEL motif"),
        _leaf("signal", "Signal peptide"),
        _combine("exported", "pexel", "signal"),
        _combine("root", "taxon", "exported", CombineOp.INTERSECT),
    )

    assert steps["root"].expanded_name == "Union: PEXEL motif, Signal peptide"
    assert steps["exported"].expanded_name is None


def test_every_step_of_a_deeper_group_is_named_in_tree_order() -> None:
    steps = _named(
        _leaf("taxon", "Genes by taxon"),
        _leaf("a", "PEXEL motif"),
        _leaf("b", "Signal peptide"),
        _leaf("c", "Transmembrane domain"),
        _combine("ab", "a", "b"),
        _combine("abc", "ab", "c"),
        _combine("root", "taxon", "abc", CombineOp.INTERSECT),
    )

    assert steps["root"].expanded_name == (
        "Union: PEXEL motif, Signal peptide, Transmembrane domain"
    )


def test_a_group_of_mixed_operators_names_its_steps_alone() -> None:
    steps = _named(
        _leaf("taxon", "Genes by taxon"),
        _leaf("a", "PEXEL motif"),
        _leaf("b", "Signal peptide"),
        _leaf("c", "Transmembrane domain"),
        _combine("ab", "a", "b", CombineOp.MINUS),
        _combine("abc", "ab", "c"),
        _combine("root", "taxon", "abc", CombineOp.INTERSECT),
    )

    assert steps["root"].expanded_name == (
        "PEXEL motif, Signal peptide, Transmembrane domain"
    )


def test_a_long_name_is_cut_on_a_word() -> None:
    steps = _named(
        _leaf("taxon", "Genes by taxon"),
        _leaf("a", "Exported proteins predicted by the ExportPred algorithm"),
        _leaf("b", "Proteins with a predicted signal peptide"),
        _combine("ab", "a", "b"),
        _combine("root", "taxon", "ab", CombineOp.INTERSECT),
    )

    assert steps["root"].expanded_name == (
        "Union: Exported proteins predicted by the ExportPred algorithm,..."
    )


def test_a_saved_strategy_keeps_its_own_name() -> None:
    steps = _named(
        _leaf("taxon", "Genes by taxon"),
        _leaf("a", "PEXEL motif"),
        _leaf("b", "Signal peptide"),
        _combine("ab", "a", "b"),
        _combine(
            "root",
            "taxon",
            "ab",
            CombineOp.INTERSECT,
            expanded_strategy_id=330659633,
            expanded_name="Exported proteome",
        ),
    )

    assert steps["root"].expanded_name == "Exported proteome"


def test_a_single_step_on_the_secondary_side_is_no_group() -> None:
    steps = _named(
        _leaf("a", "PEXEL motif"),
        _leaf("b", "Signal peptide"),
        _combine("root", "a", "b", CombineOp.INTERSECT),
    )

    assert [
        (step.id, step.display_name, step.expanded_name) for step in steps.values()
    ] == [
        ("a", "PEXEL motif", None),
        ("b", "Signal peptide", None),
        ("root", "Intersect", None),
    ]
