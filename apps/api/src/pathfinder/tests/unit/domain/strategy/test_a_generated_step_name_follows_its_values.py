"""A step name Strategist made follows the values it labels; any other name stays."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, NumberValue, ParamValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_naming import (
    StepTitle,
    TitleLabel,
    criterion_title,
)
from pathfinder.domain.strategy.step_words import StepWords

from ._builders import graph_with

_STEP = "step_go"
_KINASE = MultiPickValue(values=["GO:0004672"])
_TRANSFERASE = MultiPickValue(values=["GO:0016301"])
_KINASE_TITLE = StepTitle(
    head="GO Term",
    labels=[TitleLabel(param="GoTerm", wire=_KINASE.to_wire(), label="protein kinase")],
)
_TRANSFERASE_TITLE = StepTitle(
    head="GO Term",
    labels=[
        TitleLabel(param="GoTerm", wire=_TRANSFERASE.to_wire(), label="kinase activity")
    ],
)


def _graph(display_name: str, *, seeded: bool = True) -> StrategyGraph:
    graph = graph_with(
        [
            StrategyStepNode(
                id=_STEP,
                search_name="GenesByGoTerm",
                display_name=display_name,
                parameters={"GoTerm": _KINASE, "min_score": NumberValue(value=1)},
            )
        ]
    )
    if seeded:
        graph.note_words(StepWords(titles={_STEP: _KINASE_TITLE}))
    return graph


def _set(graph: StrategyGraph, name: str, value: ParamValue) -> None:
    apply_operation(graph, UpdateStepParamsOp(step_id=_STEP, parameters={name: value}))


def _name(graph: StrategyGraph) -> str | None:
    return graph.steps[_STEP].display_name


def test_the_generated_name_is_the_search_and_the_labels() -> None:
    assert _KINASE_TITLE.name == "GO Term: protein kinase"
    assert StepTitle(head="GO Term").name == "GO Term"


def test_a_moved_value_takes_its_label_out_of_a_generated_name() -> None:
    graph = _graph(_KINASE_TITLE.name)

    _set(graph, "GoTerm", _TRANSFERASE)

    assert _name(graph) == "GO Term"


def test_a_value_the_name_does_not_label_keeps_the_generated_name() -> None:
    graph = _graph(_KINASE_TITLE.name)

    _set(graph, "min_score", NumberValue(value=3))

    assert _name(graph) == "GO Term: protein kinase"


def test_a_rebound_value_regenerates_the_name_from_its_fresh_label() -> None:
    graph = _graph(_KINASE_TITLE.name)
    _set(graph, "GoTerm", _TRANSFERASE)

    graph.note_words(StepWords(titles={_STEP: _TRANSFERASE_TITLE}))

    assert _name(graph) == "GO Term: kinase activity"


def test_a_label_of_a_value_the_step_does_not_hold_is_left_out() -> None:
    graph = _graph(_KINASE_TITLE.name)
    _set(graph, "GoTerm", _TRANSFERASE)

    graph.note_words(StepWords(titles={_STEP: _KINASE_TITLE}))

    assert _name(graph) == "GO Term"


def test_a_name_the_researcher_wrote_is_never_rewritten() -> None:
    graph = _graph("Kinases I care about")

    _set(graph, "GoTerm", _TRANSFERASE)
    graph.note_words(StepWords(titles={_STEP: _TRANSFERASE_TITLE}))

    assert _name(graph) == "Kinases I care about"


def test_a_name_with_no_seed_is_never_rewritten() -> None:
    graph = _graph("GO Term: protein kinase", seeded=False)

    _set(graph, "GoTerm", _TRANSFERASE)
    graph.note_words(StepWords(titles={_STEP: _TRANSFERASE_TITLE}))

    assert _name(graph) == "GO Term: protein kinase"


def test_the_seed_rides_the_stored_strategy() -> None:
    graph = _graph(_KINASE_TITLE.name)

    ast = graph.to_strategy_ast()

    assert ast is not None
    assert StepWords.of(ast).titles == {_STEP: _KINASE_TITLE}


def test_stored_words_with_no_seed_and_unknown_fields_load() -> None:
    words = StepWords.model_validate(
        {"criterionTexts": {_STEP: "kinases"}, "titles": {_STEP: {"x": 1}}, "y": 2}
    )

    assert (words.criterion_texts, words.titles) == ({_STEP: "kinases"}, {})


def _criterion(**params: BoundValue) -> Criterion:
    return Criterion(
        id=_STEP,
        text="genes annotated with protein kinase activity",
        search_name="GenesByGoTerm",
        search_display_name="GO Term",
        organism_param="organism",
        resolved_params=params,
    )


def _labelled(
    value: MultiPickValue, label: str, *, visible: bool = True, at_default: bool = False
) -> BoundValue:
    return BoundValue(
        value=value,
        source="stated",
        label=label,
        visible=visible,
        at_default=at_default,
    )


def test_a_criterion_titles_its_step_by_the_search_and_the_bound_labels() -> None:
    criterion = _criterion(
        organism=_labelled(MultiPickValue(values=["Pf3D7"]), "P. falciparum 3D7"),
        GoTerm=_labelled(_KINASE, "protein kinase"),
        hidden=_labelled(_TRANSFERASE, "hidden", visible=False),
        initial=_labelled(_TRANSFERASE, "initial", at_default=True),
        min_score=BoundValue(value=NumberValue(value=1), source="stated"),
    )

    assert criterion_title(criterion) == _KINASE_TITLE


def test_a_criterion_with_no_bound_label_is_titled_by_its_search() -> None:
    assert criterion_title(_criterion()).name == "GO Term"


def test_a_long_label_list_is_cut_on_a_word() -> None:
    title = StepTitle(
        head="GO Term",
        labels=[
            TitleLabel(param=f"p{n}", wire=str(n), label=f"label number {n}")
            for n in range(9)
        ],
    )

    assert title.name == (
        "GO Term: label number 0, label number 1, label number 2, label number..."
    )
