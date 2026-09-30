"""A reply holds each count the turn measured and the difference of any two of
them: each step's count, each count before an edit, and every count a completed
comparison returned. Any other number stays refused."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.contract_messages import fact_outside_the_block_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment.variant_comparison import (
    PairwiseOverlap,
    VariantComparison,
    VariantResult,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _deps(root: StrategyStepNode, counts: dict[str, int], site_id: str) -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="strategy", site_id=site_id)
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id=site_id)
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts=dict(counts))
    state = pipeline_state(
        site_id, user_message_id=uuid4(), domain=StrategyDomainState()
    )
    return lead_deps(state, strategy_session=session)


def _printed(deps: LeadDeps, prose: str) -> list[str]:
    record = turn_record(run_context_for(deps))
    return [
        m.sentence
        for m in reconcile(reply(prose), record)
        if m.kind == "fact_outside_the_block"
    ]


def _intersect(site_id: str, left: int, right: int, root: int) -> LeadDeps:
    node = StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_sp", search_name="GenesWithSignalPeptide"
        ),
        secondary_input=StrategyStepNode(
            id="step_orth", search_name="GenesByOrthologPattern"
        ),
    )
    return _deps(
        node, {"step_sp": left, "step_orth": right, "step_join": root}, site_id
    )


# microsporidiadb: E. intestinalis signal peptide 66, the ecun exclusion 129, 9 in both.
_MICRO_REPLY = (
    "Using only the signal-peptide requirement, the search returns **66 genes**. "
    "The current signal-peptide-plus-ortholog-exclusion strategy returns **9 "
    "genes**, so removing the ortholog filter would add **57 genes**. I compared "
    "these as an anonymous result only; your strategy was not changed."
)
# toxodb: GT1 signal peptide 680, the ncan exclusion 1,240, 53 in both.
_TOXO_REPLY = (
    "The ortholog filter removed **627 genes**: the signal-peptide search returned "
    "**680 genes**, and **53** remained after applying the ortholog exclusion. "
    "Nothing in the strategy was changed."
)


def test_the_difference_of_a_step_and_the_result_is_held() -> None:
    assert _printed(_intersect("microsporidiadb", 66, 129, 9), _MICRO_REPLY) == []
    assert _printed(_intersect("toxodb", 680, 1240, 53), _TOXO_REPLY) == []


def test_a_number_no_two_counts_give_is_refused() -> None:
    deps = _intersect("toxodb", 680, 1240, 53)

    assert _printed(deps, "The ortholog filter removed 628 genes.") == [
        fact_outside_the_block_message(["628"])
    ]
    assert _printed(deps, "About 16% of the 680 remain.") == [
        fact_outside_the_block_message(["16%"])
    ]


def test_the_difference_of_a_count_and_its_count_before_the_edit_is_held() -> None:
    """veupathdb: the GO term step narrowed from 12 genes to 7 at 3D7."""
    deps = _deps(
        StrategyStepNode(id="step_go", search_name="GenesByGoTerm"),
        {"step_go": 7},
        "veupathdb",
    )
    markers = deps.state.turn_markers
    markers.record_arrival("step_go", {"step_go": 12})
    markers.edited = True
    prose = (
        "The narrowed strategy returns 7 genes. The original across-*Plasmodium* "
        "search returned 12 genes, so narrowing to 3D7 reduces the result by 5 genes."
    )

    assert _printed(deps, prose) == []
    assert _printed(deps, "Narrowing removed 6 genes.") == [
        fact_outside_the_block_message(["6"])
    ]


def _mucin_comparison() -> VariantComparison:
    """cryptodb: mucin* in the product field alone, then in every text field."""
    return VariantComparison(
        variants=[
            VariantResult(
                label="Product field only",
                search_name="GenesByText",
                gene_count=2,
                unique_count=0,
                sample_unique_genes=[],
                result_count=2,
            ),
            VariantResult(
                label="All text fields",
                search_name="GenesByText",
                gene_count=84,
                unique_count=82,
                sample_unique_genes=["CPATCC_0000430"],
                result_count=84,
            ),
        ],
        overlaps=[
            PairwiseOverlap(
                a="Product field only", b="All text fields", shared=2, jaccard=0.0238
            )
        ],
    )


def test_every_count_a_comparison_returned_is_held() -> None:
    deps = _deps(
        StrategyStepNode(id="step_text", search_name="GenesByText"),
        {"step_text": 2},
        "cryptodb",
    )
    deps.state.turn_markers.record_comparison(_mucin_comparison())
    prose = (
        "Searching all text fields finds substantially more matches than searching "
        "the product field alone: 84 genes versus 2. The broader search contains "
        "the 2 product-field hits plus 82 additional genes, with very little "
        "overlap relative to the broader result."
    )

    assert _printed(deps, prose) == []


def test_a_comparison_counts_its_genes_results_unique_and_shared() -> None:
    assert _mucin_comparison().counts() == frozenset({2, 84, 0, 82})


def test_the_refusal_names_the_tokens_and_keeps_the_counts_the_facts_show() -> None:
    message = fact_outside_the_block_message(["57"])

    assert (
        "``57``" in message,
        "every count the facts show" in message,
        "prints no number" in message,
        "left out" in message,
    ) == (True, True, False, False)
