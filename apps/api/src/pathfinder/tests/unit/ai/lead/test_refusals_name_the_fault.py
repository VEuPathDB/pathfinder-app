"""Every refusal names the thing at fault, and says what did not change.

Each message is checked for the four properties it owes: what happened, whose
fault it is, whether the strategy moved, and what the model does next.
"""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.ai.lead._delete_rules import (
    DeleteSurface,
    refuse_a_delete_the_graph_cannot_place,
)
from pathfinder.ai.lead.build_messages import structure_does_not_convert_message
from pathfinder.ai.lead.dispatch_messages import (
    option_binds_no_step_message,
    undeclared_spec_changes,
)
from pathfinder.ai.lead.edit_messages import (
    edit_bound_nothing_message,
    edit_operation_refused_message,
    unsupported_edit_message,
)
from pathfinder.ai.tools.standalone.strategy_refusals import (
    build_departs_from_the_plan_message,
    operation_refused_message,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import CriterionChange, diff_specs

# What no refusal of an edit or a build may offer as a way out.
_REBUILD_WORDS = ("rebuild", "replace", "from scratch", "start over")
_THE_GRAPH_SAID = "leaf 'step_1a2b3c4d' not found"
_THE_SHAPE_SAID = "the tree states a step the strategy does not hold"
_THE_PLAN_SAID = (
    "the spec joins ['c_mass_spec', 'c_text'] at INTERSECT, and this write "
    "joins them at UNION, so the strategy would answer a different question."
)
_THE_TREE_SAID = "a combine names no operator"


def _offers_a_rebuild(message: str) -> bool:
    lowered = message.casefold()
    return any(word in lowered for word in _REBUILD_WORDS)


class TestAnEditTheShapeCannotTake:
    """The shape refusal keeps its subject and offers no replacement."""

    def test_it_names_the_shape_and_quotes_what_was_wrong(self) -> None:
        message = unsupported_edit_message(_THE_SHAPE_SAID)

        assert "does not map onto the strategy's steps" in message
        assert _THE_SHAPE_SAID in message

    def test_it_says_the_strategy_did_not_move(self) -> None:
        assert "Nothing was applied" in unsupported_edit_message(_THE_SHAPE_SAID)

    def test_it_offers_no_rebuild(self) -> None:
        assert _offers_a_rebuild(unsupported_edit_message(_THE_SHAPE_SAID)) is False


class TestAnOperationTheEditWrites:
    """An operation refused before VEuPathDB is asked blames that operation."""

    def test_it_names_the_operation_this_edit_writes(self) -> None:
        message = edit_operation_refused_message(_THE_GRAPH_SAID)

        assert "operation this edit writes" in message
        assert _THE_GRAPH_SAID in message

    def test_it_blames_neither_the_shape_nor_the_site(self) -> None:
        message = edit_operation_refused_message(_THE_GRAPH_SAID)

        assert "does not map onto the strategy's steps" not in message
        assert "VEuPathDB refused" not in message

    def test_it_says_the_strategy_did_not_move(self) -> None:
        message = edit_operation_refused_message(_THE_GRAPH_SAID)

        assert "Nothing was applied" in message
        assert "every step and every value it held" in message

    def test_it_names_the_way_forward_and_forbids_a_rebuild(self) -> None:
        message = edit_operation_refused_message(_THE_GRAPH_SAID)

        assert "set_criterion" in message
        assert "Do not offer to rebuild the strategy from scratch" in message


class TestAnEditThatBoundNothing:
    def test_it_says_the_strategy_did_not_move(self) -> None:
        assert "Nothing was applied" in edit_bound_nothing_message()


def _spec_with_an_unplaced_option() -> OperationalSpec:
    """A plan whose option states a value on a search no step in it runs."""
    return OperationalSpec(
        goal="odorant binding proteins",
        criteria=[
            Criterion(
                id="c_text",
                text="odorant binding protein",
                search_name="GenesByText",
                role="seed",
            ),
            Criterion(
                id="c_option",
                text="restrict to Anopheles gambiae",
                search_name="GenesByTaxon",
                resolved_params={
                    "organism": MultiPickValue(values=["Anopheles gambiae PEST"])
                },
            ),
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c_text")),
    )


class TestAnOptionNoStepCarries:
    def test_it_says_nothing_was_built(self) -> None:
        spec = _spec_with_an_unplaced_option()

        message = option_binds_no_step_message(spec, ["c_option"])

        assert "Nothing was built" in message

    def test_it_still_names_the_criterion_at_fault(self) -> None:
        spec = _spec_with_an_unplaced_option()

        assert "c_option" in option_binds_no_step_message(spec, ["c_option"])


def _two_criteria() -> OperationalSpec:
    return OperationalSpec(
        goal="proteases",
        criteria=[
            Criterion(id="step_a", text="protease text", search_name="GenesByText"),
            Criterion(id="step_b", text="proteolysis GO", search_name="GenesByGoTerm"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_a"),
                    StructureNode(kind="leaf", criterion_id="step_b"),
                ],
            )
        ),
    )


class TestAnAccountThatDoesNotMatchTheDraft:
    def test_it_says_the_strategy_did_not_move(self) -> None:
        before = _two_criteria()
        after = before.model_copy(deep=True)
        after.criteria = [after.criteria[0]]

        problem = undeclared_spec_changes(
            diff_specs(before, after),
            [CriterionChange(criterion_id="step_b", disposition="kept")],
            before,
        )

        assert "Nothing was applied" in problem
        assert "step_b" in problem


class TestABuildTheTreeCannotHold:
    def test_it_names_the_structure_and_says_nothing_was_built(self) -> None:
        message = structure_does_not_convert_message(_THE_TREE_SAID)

        assert _THE_TREE_SAID in message
        assert "Nothing was built" in message
        assert "set_structure" in message


class TestABuildThatDepartsFromThePlan:
    def test_it_names_the_plan_and_spares_the_site(self) -> None:
        message = build_departs_from_the_plan_message(_THE_PLAN_SAID)

        assert _THE_PLAN_SAID in message
        assert "VEuPathDB was not asked" in message

    def test_it_says_nothing_was_built(self) -> None:
        assert "Nothing was built" in build_departs_from_the_plan_message(
            _THE_PLAN_SAID
        )

    def test_it_does_not_read_as_an_external_rejection(self) -> None:
        assert "REJECTED" not in build_departs_from_the_plan_message(_THE_PLAN_SAID)


class TestABatchTheGraphRefused:
    """A rolled-back batch names the operation, not the site and not the user."""

    def test_it_names_what_the_caller_wrote(self) -> None:
        message = operation_refused_message(_THE_GRAPH_SAID, wrote="batch")

        assert "operation this batch writes" in message
        assert _THE_GRAPH_SAID in message

    def test_it_says_nothing_moved_and_spares_the_site(self) -> None:
        message = operation_refused_message(_THE_GRAPH_SAID, wrote="export")

        assert "Nothing was applied" in message
        assert "VEuPathDB was not asked" in message

    def test_it_does_not_read_as_an_external_rejection(self) -> None:
        message = operation_refused_message(_THE_GRAPH_SAID, wrote="batch")

        assert "REJECTED" not in message


def _two_rooted_thread() -> StrategyGraph:
    """A thread holding two roots, neither of them pushed."""
    graph = StrategyGraph(graph_id="g1", name="two roots", site_id="plasmodb")
    graph.steps = {
        "step_1": StrategyStep(
            id="step_1", kind=StepKind.SEARCH, search_name="GenesByText"
        ),
        "step_2": StrategyStep(
            id="step_2", kind=StepKind.SEARCH, search_name="GenesByGoTerm"
        ),
        "step_3": StrategyStep(
            id="step_3",
            kind=StepKind.COMBINE,
            operator=CombineOp.INTERSECT,
            primary_input_id="step_1",
            secondary_input_id="step_2",
        ),
        "step_4": StrategyStep(
            id="step_4", kind=StepKind.SEARCH, search_name="GenesByTaxon"
        ),
        "step_5": StrategyStep(
            id="step_5", kind=StepKind.SEARCH, search_name="GenesByLocation"
        ),
        "step_6": StrategyStep(
            id="step_6",
            kind=StepKind.COMBINE,
            operator=CombineOp.INTERSECT,
            primary_input_id="step_4",
            secondary_input_id="step_5",
        ),
    }
    graph.recompute_roots()
    return graph


class TestADeleteTheThreadCannotPlace:
    def test_the_ambiguous_root_refusal_says_nothing_was_removed(self) -> None:
        graph = _two_rooted_thread()

        with pytest.raises(ModelRetry) as excinfo:
            refuse_a_delete_the_graph_cannot_place(
                graph, None, "step_3", DeleteSurface.LEAD
            )

        found = str(excinfo.value)
        assert "Nothing was removed" in found
        assert "step_3" in found
