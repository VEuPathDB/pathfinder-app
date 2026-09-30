"""The answer revision moves with what the root computes and nothing else."""

from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.revision import answer_revision


def _leaf(step_id: str, name: str = "") -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name="GenesByText", display_name=name)


def _ast(
    operator: CombineOp, *, detached: list[StrategyStepNode], name: str = ""
) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_root",
            search_name="__combine__",
            primary_input=_leaf("step_a", name),
            secondary_input=_leaf("step_b"),
            operator=operator,
        ),
        detached_roots=detached,
    )


def test_a_rename_and_an_uncombined_step_leave_the_answer_revision() -> None:
    before = _ast(CombineOp.UNION, detached=[])
    after = _ast(CombineOp.UNION, detached=[_leaf("step_c")], name="Renamed step")

    assert answer_revision(after) == answer_revision(before)


def test_an_operator_change_moves_the_answer_revision() -> None:
    before = _ast(CombineOp.UNION, detached=[])
    after = _ast(CombineOp.INTERSECT, detached=[])

    assert (
        answer_revision(None),
        answer_revision(after) == answer_revision(before),
    ) == (
        "",
        False,
    )
