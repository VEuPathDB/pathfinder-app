"""A step's name never states a parameter value the step no longer holds."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph

from ._builders import graph_with

_TRANSMEMBRANE = "step_4f51bc4f"
_NAMED_FOR_SEVEN = (
    "Genes with 1 to 7 predicted transmembrane domains across all Toxoplasma"
)


def _transmembrane_graph(display_name: str) -> StrategyGraph:
    return graph_with(
        [
            StrategyStepNode(
                id=_TRANSMEMBRANE,
                search_name="GenesByTransmembraneDomains",
                display_name=display_name,
                parameters={
                    "min_tm": NumberValue(value=1),
                    "max_tm": NumberValue(value=7),
                },
            )
        ]
    )


def _set_max_tm(graph: StrategyGraph, value: int) -> None:
    apply_operation(
        graph,
        UpdateStepParamsOp(
            step_id=_TRANSMEMBRANE, parameters={"max_tm": NumberValue(value=value)}
        ),
    )


class TestAParameterWriteRestatesTheName:
    def test_the_name_states_the_value_the_step_now_holds(self) -> None:
        graph = _transmembrane_graph(_NAMED_FOR_SEVEN)

        _set_max_tm(graph, 2)

        assert graph.steps[_TRANSMEMBRANE].display_name == (
            "Genes with 1 to 2 predicted transmembrane domains across all Toxoplasma"
        )

    def test_a_name_that_states_no_moved_value_is_left_alone(self) -> None:
        graph = _transmembrane_graph("Membrane candidates I care about")

        _set_max_tm(graph, 2)

        assert (
            graph.steps[_TRANSMEMBRANE].display_name
            == "Membrane candidates I care about"
        )

    def test_a_value_inside_a_word_is_not_a_stated_value(self) -> None:
        graph = _transmembrane_graph("Genes like TGME49_207 with 7 domains")

        _set_max_tm(graph, 2)

        assert (
            graph.steps[_TRANSMEMBRANE].display_name
            == "Genes like TGME49_207 with 2 domains"
        )

    def test_a_parameter_the_write_leaves_alone_states_its_own_value(self) -> None:
        """Only a value the write moves is restated."""
        graph = _transmembrane_graph(_NAMED_FOR_SEVEN)

        apply_operation(
            graph,
            UpdateStepParamsOp(
                step_id=_TRANSMEMBRANE,
                parameters={"organism": StringValue(value="Toxoplasma gondii ME49")},
            ),
        )

        assert graph.steps[_TRANSMEMBRANE].display_name == _NAMED_FOR_SEVEN


class TestARewriteReadsTheNameItFound:
    """Every value is restated against the name the write found, in one pass."""

    def test_a_range_whose_new_low_was_the_old_high_states_both(self) -> None:
        graph = _transmembrane_graph(
            "Genes with 1 to 7 predicted transmembrane domains across all"
        )

        apply_operation(
            graph,
            UpdateStepParamsOp(
                step_id=_TRANSMEMBRANE,
                parameters={
                    "min_tm": NumberValue(value=7),
                    "max_tm": NumberValue(value=12),
                },
            ),
        )

        assert graph.steps[_TRANSMEMBRANE].display_name == (
            "Genes with 7 to 12 predicted transmembrane domains across all"
        )

    def test_a_literal_the_name_states_twice_identifies_no_parameter(self) -> None:
        """A stale name beats a fabricated one."""
        graph = _transmembrane_graph("Genes with 1 to 7 domains in 7 or more strains")

        _set_max_tm(graph, 9)

        assert graph.steps[_TRANSMEMBRANE].display_name == (
            "Genes with 1 to 7 domains in 7 or more strains"
        )

    def test_two_parameters_that_moved_the_same_value_apart_are_left_alone(
        self,
    ) -> None:
        graph = graph_with(
            [
                StrategyStepNode(
                    id=_TRANSMEMBRANE,
                    search_name="GenesByTransmembraneDomains",
                    display_name="Genes with 3 domains",
                    parameters={
                        "min_tm": NumberValue(value=3),
                        "max_tm": NumberValue(value=3),
                    },
                )
            ]
        )

        apply_operation(
            graph,
            UpdateStepParamsOp(
                step_id=_TRANSMEMBRANE,
                parameters={
                    "min_tm": NumberValue(value=1),
                    "max_tm": NumberValue(value=9),
                },
            ),
        )

        assert graph.steps[_TRANSMEMBRANE].display_name == "Genes with 3 domains"
