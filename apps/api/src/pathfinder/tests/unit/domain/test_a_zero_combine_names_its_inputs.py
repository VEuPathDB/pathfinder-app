"""A combine that holds no record over inputs that hold some says why from the
counts: the records of one input are not among the other's."""

from __future__ import annotations

from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep
from veupathdb.domain.strategy.ops import CombineOp

from pathfinder.domain.zero_combine import zero_combine_caveats


def _search(step_id: str, name: str) -> StrategyStep:
    return StrategyStep(
        id=step_id, kind=StepKind.SEARCH, search_name=step_id, display_name=name
    )


def _combine(operator: CombineOp) -> dict[str, StrategyStep]:
    return {
        "step_0c6996fa": _search("step_0c6996fa", "Text"),
        "step_6a264618": _search("step_6a264618", "Predicted Signal Peptide"),
        "step_root": StrategyStep(
            id="step_root",
            kind=StepKind.COMBINE,
            operator=operator,
            primary_input_id="step_0c6996fa",
            secondary_input_id="step_6a264618",
        ),
    }


def _sentences(operator: CombineOp, text: int, signal: int, combined: int) -> list[str]:
    counts = {"step_0c6996fa": text, "step_6a264618": signal, "step_root": combined}
    return [
        caveat.sentence
        for caveat in zero_combine_caveats(_combine(operator), counts, "gene")
    ]


def test_an_empty_intersect_says_the_one_gene_is_not_among_the_others() -> None:
    """The piroplasmadb AND: 1 text hit, 288 signal peptide genes, 0 in both."""
    assert _sentences(CombineOp.INTERSECT, 1, 288, 0) == [
        (
            "INTERSECT holds 0 genes: the 1 gene of 'Text' is not among the 288 "
            "of 'Predicted Signal Peptide'"
        )
    ]


def test_an_empty_intersect_of_larger_inputs_names_both_counts() -> None:
    assert _sentences(CombineOp.INTERSECT, 1_204, 421, 0) == [
        (
            "INTERSECT holds 0 genes: none of the 421 genes of 'Predicted Signal "
            "Peptide' is among the 1,204 of 'Text'"
        )
    ]


def test_an_empty_minus_says_every_record_is_among_the_others() -> None:
    assert _sentences(CombineOp.MINUS, 5, 288, 0) == [
        (
            "MINUS holds 0 genes: all 5 genes of 'Text' are among the 288 of "
            "'Predicted Signal Peptide'"
        )
    ]


def test_a_combine_with_an_empty_input_or_records_says_nothing() -> None:
    assert _sentences(CombineOp.INTERSECT, 0, 288, 0) == []
    assert _sentences(CombineOp.INTERSECT, 1, 288, 1) == []
