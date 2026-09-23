"""A case reads the final strategy's root operator and its count against its inputs."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.scoring import (
    ObservedOutcome,
    final_count_below_every_input,
    root_operator,
    score_case,
)
from pathfinder.evals.store import load_case

_CASE = "requirements-joined-by-commas-intersect"


def _leaf(search_name: str) -> StrategyStepNode:
    return StrategyStepNode(search_name=search_name)


def _combine(
    left: StrategyStepNode, op: CombineOp, right: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="__combine__",
        primary_input=left,
        secondary_input=right,
        operator=op,
    )


def _counted(op: CombineOp, final: int, inputs: tuple[int, int, int]) -> StrategyAst:
    stage, surface, proteomics = (
        _leaf("GenesByRNASeqEvidence"),
        _leaf("GenesBySignalPeptide"),
        _leaf("GenesByMassSpec"),
    )
    inner = _combine(stage, op, surface)
    root = _combine(inner, op, proteomics)
    counts = dict(zip((stage.id, surface.id, proteomics.id), inputs, strict=True))
    return StrategyAst(
        record_type="transcript",
        root=root,
        step_counts={**counts, inner.id: final + 1, root.id: final},
    )


def _observed(ast: StrategyAst) -> ObservedOutcome:
    return ObservedOutcome(
        built_strategy=True,
        root_operator=root_operator(ast),
        final_count_below_every_input=final_count_below_every_input(ast),
    )


def _case(*, operator: str | None = "INTERSECT", below: bool | None = True) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["build something"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the combine",
        expected=ExpectedOutcome(
            builds_strategy=True,
            root_operator=operator,
            final_count_below_every_input=below,
        ),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-09-23",
        ),
    )


def test_an_intersect_below_every_input_passes() -> None:
    observed = _observed(_counted(CombineOp.INTERSECT, 2, (479, 4480, 71)))

    score = score_case(_case(), observed)

    assert observed.root_operator == "INTERSECT"
    assert observed.final_count_below_every_input is True
    assert score.passed is True


def test_a_union_above_its_inputs_fails_on_both_facts() -> None:
    observed = _observed(_counted(CombineOp.UNION, 4732, (479, 4480, 71)))

    score = score_case(_case(), observed)

    assert score.passed is False
    assert [(d.field, d.expected, d.actual) for d in score.differences] == [
        ("rootOperator", "INTERSECT", "UNION"),
        ("finalCountBelowEveryInput", "True", "False"),
    ]


def test_a_final_count_equal_to_an_input_is_not_below_it() -> None:
    ast = _counted(CombineOp.INTERSECT, 71, (479, 4480, 71))

    assert final_count_below_every_input(ast) is False


def test_missing_counts_are_not_read_as_below() -> None:
    ast = _counted(CombineOp.INTERSECT, 2, (479, 4480, 71)).model_copy(
        update={"step_counts": None}
    )
    observed = _observed(ast)

    assert observed.final_count_below_every_input is None
    assert score_case(_case(below=None), observed).passed is True
    assert [d.field for d in score_case(_case(), observed).differences] == [
        "finalCountBelowEveryInput"
    ]


def test_a_single_step_has_no_root_operator_and_no_inputs() -> None:
    leaf = _leaf("GenesByText")
    ast = StrategyAst(record_type="transcript", root=leaf, step_counts={leaf.id: 9})

    read = (root_operator(ast), final_count_below_every_input(ast))

    assert read == (None, None)


def test_the_shipped_case_expects_an_intersect_below_its_inputs() -> None:
    case = load_case(_CASE)

    assert case.expected.builds_strategy is True
    assert case.expected.root_operator == "INTERSECT"
    assert case.expected.final_count_below_every_input is True
