"""A criterion's links to the requirements it answers ride the stored words of
its step, and a step that runs another search keeps the requirements alone."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyAst

from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
)
from strategist.domain.strategy.spec_hydration import spec_from_ast
from strategist.domain.strategy.spec_replay import criterion_rebound
from strategist.domain.strategy.step_words import StepWords, step_words

from ._builders import graph_of, spec_leaf, text_leaf, three_step_root

_LINK = RequirementLink(requirement="a1b2c3d4e5f6", param="text_expression")
_TEXT = Criterion(
    id="c_text",
    text="protease genes",
    search_name="GenesByText",
    answers=[_LINK],
)


def test_the_graph_stores_the_links_and_hydrates_them_back() -> None:
    graph = graph_of(three_step_root())
    spec = OperationalSpec(
        goal="g", criteria=[_TEXT], structure=SpecStructure(root=spec_leaf("c_text"))
    )
    graph.note_words(step_words(spec, {"c_text": "step_text"}))
    ast = graph.to_strategy_ast()
    assert isinstance(ast, StrategyAst)

    held = {c.id: c.answers for c in spec_from_ast(ast, goal="g", listed={}).criteria}

    assert (StepWords.of(ast).answers, held["step_text"], held["step_go"]) == (
        {"step_text": [_LINK]},
        [_LINK],
        [],
    )


def test_a_step_that_runs_another_search_keeps_the_requirement_and_no_param() -> None:
    rebound = criterion_rebound(
        _TEXT, text_leaf().model_copy(update={"search_name": "GenesByGoTerm"}), None
    )

    assert rebound.answers == [RequirementLink(requirement=_LINK.requirement)]
