"""A served step says why it runs what it runs: the stored search choice, or
the compute its own analysis document holds."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb.eda import EdaAnalysisDetail

from pathfinder.ai.tools.standalone.graph_helpers import build_step_response
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_rationale import (
    AnalysisRationale,
    ComparedSearch,
    SearchRationale,
)
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.services.eda.export import eda_step_request
from pathfinder.services.strategies.schemas import step_response_from_strategy_ast
from pathfinder.tests._support.eda_wire import fixture

_EXPORTED = "GenesByExportPrediction"
_COMPUTE = "GenesByEdaVizWithCompute"
_DATASET = "DS_e973eadd57"
_CHOSEN = SearchRationale(
    search_name=_EXPORTED,
    basis="nearest",
    term="GPI anchor",
    reason="no search states a GPI anchor; Exported Protein is the nearest",
    similarity=0.44,
    compared=[
        ComparedSearch(
            name="GenesByText", display_name="Gene Text Search", similarity=0.41
        )
    ],
    answered=20,
    query="genes with a predicted GPI anchor",
    tool_call_id="call_gpi",
)


def _leaf(step_id: str, search_name: str = _EXPORTED) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name)


def _stored(root: StrategyStepNode, words: StepWords | None) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=root,
        metadata=None if words is None else words.model_dump(by_alias=True),
    )


def _exported_step() -> StrategyStepNode:
    """A DESeq comparison of normal against febrile, as the export wrote it."""
    detail = EdaAnalysisDetail.model_validate(fixture("analysis_detail_pass_and_de"))
    request = eda_step_request(
        detail,
        dataset_id=_DATASET,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
    )
    return StrategyStepNode(
        id="step_de",
        search_name=_COMPUTE,
        parameters={
            name: StringValue(value=value)
            for name, value in request.wdk_parameters().items()
        },
    )


def test_a_stored_step_answers_with_its_search_choice() -> None:
    ast = _stored(_leaf("step_a"), StepWords(rationales={"step_a": _CHOSEN}))

    assert step_response_from_strategy_ast(ast, ast.root).rationale == _CHOSEN


def test_a_live_step_answers_with_its_search_choice() -> None:
    graph = StrategyGraph("g1", "GPI", "plasmodb")
    graph.steps.update(flatten_tree(_leaf("step_a")))
    graph.recompute_roots()
    graph.note_words(StepWords(rationales={"step_a": _CHOSEN}))

    assert build_step_response(graph, graph.steps["step_a"]).rationale == _CHOSEN


def test_a_step_the_site_moved_to_another_search_answers_no_reason() -> None:
    ast = _stored(
        _leaf("step_a", "GenesByTaxon"), StepWords(rationales={"step_a": _CHOSEN})
    )

    response = step_response_from_strategy_ast(ast, ast.root)

    assert (response.search_name, response.rationale) == ("GenesByTaxon", None)


def test_a_re_imported_search_step_answers_no_reason() -> None:
    ast = _stored(_leaf("step_a"), None)

    response = step_response_from_strategy_ast(ast, ast.root)

    assert (response.search_name, response.rationale) == (_EXPORTED, None)


def test_a_re_imported_analysis_step_answers_its_compute() -> None:
    step = _exported_step()
    stamped = StampedKind(search_name=_COMPUTE, kind=AnalysisKind.COMPUTE)
    ast = _stored(step, StepWords(analysis_kinds={step.id: stamped}))

    assert step_response_from_strategy_ast(ast, ast.root).rationale == (
        AnalysisRationale(
            dataset_id=_DATASET,
            method="DESeq",
            term="DESeq",
            reason=(
                "Genes that differ between normal and febrile "
                "(DESeq, |effect| >= 1, p <= 0.05)"
            ),
        )
    )
