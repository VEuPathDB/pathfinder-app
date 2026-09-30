"""A combine that holds no record over inputs that hold some is a caveat of the
facts part, named by its inputs and their counts."""

from __future__ import annotations

from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode

from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.tests.unit.ai.lead.test_the_facts_hold_the_thread import _deps, _session


def test_an_empty_intersection_of_two_filled_inputs_is_a_caveat() -> None:
    """The piroplasmadb GPI text step (1 gene) INTERSECT the signal peptide (288)."""
    root = StrategyStepNode(
        id="step_and",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_text", search_name="GenesByText", display_name="Text"
        ),
        secondary_input=StrategyStepNode(
            id="step_sp",
            search_name="GenesWithSignalPeptide",
            display_name="Predicted Signal Peptide",
        ),
    )
    deps = _deps(
        _session(root, {"step_text": 1, "step_sp": 288, "step_and": 0}),
        site_id="piroplasmadb",
    )

    assert [
        c.sentence for c in turn_facts(deps).caveats if c.kind == "zero_combine"
    ] == [
        (
            "INTERSECT holds 0 genes: the 1 gene of 'Text' is not among the 288 of "
            "'Predicted Signal Peptide'"
        )
    ]
