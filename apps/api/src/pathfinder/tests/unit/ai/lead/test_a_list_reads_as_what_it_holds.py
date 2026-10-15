"""A value that names an uploaded list reads in the facts as what the list holds,
never as the site's id for the list."""

from __future__ import annotations

from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    domain_answering,
    lead_deps,
    pipeline_state,
)

_STEP = "c_strain_gaps"


def _row(label: str) -> list[str]:
    spec = OperationalSpec(
        goal="genes of a saved set",
        criteria=[
            Criterion(
                id=_STEP,
                text="the genes of my set",
                search_name="GeneByLocusTag",
                search_display_name="Gene set: 3D7 strain gaps",
                resolved_params={
                    "ds_gene_ids": BoundValue(
                        value=InputDatasetValue(dataset_id="202375010"),
                        source="chosen",
                        basis="the saved gene set 3D7 strain gaps",
                        label=label,
                    )
                },
                param_display_names={"ds_gene_ids": "Genes"},
            )
        ],
    )
    graph = StrategyGraph(graph_id="g1", name="gaps", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id=_STEP, search_name="GeneByLocusTag"))
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={_STEP: 300})
    state = pipeline_state("plasmodb", domain=domain_answering(spec))
    [step] = turn_facts(lead_deps(state, strategy_session=session)).steps
    [row] = step.parameters
    return row.lines()[:1]


def test_a_list_with_a_label_reads_as_its_label() -> None:
    assert _row("300 of the 300 genes of 3D7 strain gaps, saved on OrthoMCL") == [
        "Genes: 300 of the 300 genes of 3D7 strain gaps, saved on OrthoMCL"
    ]


def test_a_list_without_a_label_reads_as_an_uploaded_list() -> None:
    assert _row("") == ["Genes: an uploaded list"]
