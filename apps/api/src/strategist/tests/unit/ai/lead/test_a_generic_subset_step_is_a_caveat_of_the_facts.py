from __future__ import annotations

from veupathdb.domain.strategy import COMBINE_SEARCH_NAME, CombineOp, StrategyStepNode

from strategist.ai.lead.turn_facts import turn_facts
from strategist.tests.unit.ai.lead.test_the_facts_hold_the_thread import _deps, _session


def test_a_step_on_the_generic_subset_search_is_a_caveat() -> None:
    root = StrategyStepNode(
        id="step_and",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_orth",
            search_name="GenesByOrthologPattern",
            display_name="Ortholog pattern",
        ),
        secondary_input=StrategyStepNode(
            id="step_crispr",
            search_name="GenesByEdaSubset",
            display_name="CRISPR screen subset",
        ),
    )
    deps = _deps(
        _session(root, {"step_orth": 7880, "step_crispr": 2390, "step_and": 610}),
        site_id="toxodb",
    )

    assert [
        c.sentence for c in turn_facts(deps).caveats if c.kind == "unrevisable_subset"
    ] == [
        (
            "The site's Revise form cannot edit the dataset filter of "
            "'CRISPR screen subset'; ask Strategist to change it."
        )
    ]
