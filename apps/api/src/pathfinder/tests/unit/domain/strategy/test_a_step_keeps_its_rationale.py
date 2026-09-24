"""A criterion's search choice rides the spec and the stored words of its step."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyAst

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.spec_hydration import (
    criterion_analysing,
    spec_from_ast,
)
from pathfinder.domain.strategy.spec_replay import criterion_rebound
from pathfinder.domain.strategy.step_rationale import (
    AnalysisRationale,
    ComparedSearch,
    SearchRationale,
)
from pathfinder.domain.strategy.step_words import (
    AddedSearch,
    StepWords,
    added_searches,
    step_words,
)
from pathfinder.tests.unit.domain.strategy._analysis import COMPUTE_SEARCH, binding

from ._builders import graph_of, spec_leaf, text_leaf, three_step_root

_CHOSEN = SearchRationale(
    search_name="GenesByText",
    basis="parameter",
    term="Text term",
    reason="sets Text term to protease",
    similarity=0.62,
    compared=[
        ComparedSearch(name="GenesByGoTerm", display_name="GO Term", similarity=0.51)
    ],
    answered=12,
    query="protease genes",
    tool_call_id="call_7",
)
_TEXT = Criterion(
    id="c_text",
    text="protease genes",
    search_name="GenesByText",
    search_display_name="Gene Text Search",
    rationale=_CHOSEN,
)


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="g",
        criteria=list(criteria),
        structure=SpecStructure(root=spec_leaf(criteria[0].id)),
    )


def test_the_words_carry_each_criterions_reason_by_the_step_it_built() -> None:
    words = step_words(_spec(_TEXT), {"c_text": "step_text"})

    assert (words.criterion_texts, words.rationales) == (
        {"step_text": "protease genes"},
        {"step_text": _CHOSEN},
    )


def test_an_analysis_criterion_gives_its_compute_as_its_reason() -> None:
    analysed = criterion_analysing(_TEXT, COMPUTE_SEARCH, binding())

    assert (analysed.rationale, analysed.step_rationale) == (
        None,
        AnalysisRationale.of(binding()),
    )


def test_a_search_the_site_rebound_holds_no_reason() -> None:
    rebound = criterion_rebound(
        _TEXT, text_leaf().model_copy(update={"search_name": "GenesByGoTerm"}), None
    )

    assert (rebound.search_name, rebound.step_rationale) == ("GenesByGoTerm", None)


def test_an_added_search_carries_its_reason() -> None:
    assert added_searches(_spec(_TEXT), {"c_text"}) == [
        AddedSearch(
            step_id="c_text",
            search_display_name="Gene Text Search",
            criterion_text="protease genes",
            rationale=_CHOSEN,
        )
    ]


def test_the_graph_stores_the_reason_and_hydrates_it_back() -> None:
    graph = graph_of(three_step_root())
    graph.note_words(step_words(_spec(_TEXT), {"c_text": "step_text"}))
    ast = graph.to_strategy_ast()
    assert isinstance(ast, StrategyAst)

    held = {c.id: c.rationale for c in spec_from_ast(ast, goal="g").criteria}

    assert (StepWords.of(ast).rationales, held["step_text"], held["step_go"]) == (
        {"step_text": _CHOSEN},
        _CHOSEN,
        None,
    )


def test_a_step_that_runs_another_search_now_holds_no_reason() -> None:
    graph = graph_of(three_step_root())
    graph.note_words(StepWords(rationales={"step_go": _CHOSEN}))
    ast = graph.to_strategy_ast()
    assert isinstance(ast, StrategyAst)

    held = {c.id: c.rationale for c in spec_from_ast(ast, goal="g").criteria}

    assert held == {"step_text": None, "step_go": None, "step_expr": None}


def test_newer_words_replace_a_steps_reason_and_forget_a_removed_step() -> None:
    graph = graph_of(three_step_root())
    graph.note_words(StepWords(rationales={"step_text": _CHOSEN, "gone": _CHOSEN}))
    rebound = _CHOSEN.model_copy(update={"reason": "sets Text term to kinase"})

    graph.note_words(StepWords(rationales={"step_text": rebound}))

    assert graph.words.rationales == {"step_text": rebound}


def test_words_that_speak_for_a_step_without_a_reason_drop_the_old_one() -> None:
    graph = graph_of(three_step_root())
    graph.note_words(StepWords(rationales={"step_text": _CHOSEN}))

    graph.note_words(StepWords(criterion_texts={"step_text": "proteases again"}))

    assert (graph.words.criterion_texts, graph.words.rationales) == (
        {"step_text": "proteases again"},
        {},
    )


def test_words_about_other_steps_keep_a_steps_reason() -> None:
    graph = graph_of(three_step_root())
    graph.note_words(StepWords(rationales={"step_text": _CHOSEN}))

    graph.note_words(StepWords(criterion_texts={"step_go": "proteolysis"}))

    assert graph.words.rationales == {"step_text": _CHOSEN}


def test_a_strategy_with_no_metadata_holds_no_reason() -> None:
    ast = StrategyAst(record_type="transcript", root=three_step_root())

    assert [c.rationale for c in spec_from_ast(ast, goal="g").criteria] == [
        None,
        None,
        None,
    ]


def test_words_stored_before_reasons_existed_read_back_with_none() -> None:
    ast = StrategyAst(
        record_type="transcript",
        root=three_step_root(),
        metadata={"criterionTexts": {"step_text": "protease genes"}},
    )

    assert StepWords.of(ast) == StepWords(
        criterion_texts={"step_text": "protease genes"}
    )


def test_a_stored_reason_that_does_not_parse_is_absent() -> None:
    ast = StrategyAst(
        record_type="transcript",
        root=three_step_root(),
        metadata={"rationales": {"step_text": {"kind": "search", "basis": "vibes"}}},
    )

    assert StepWords.of(ast).rationales == {}
