from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails
from veupathdb_mcp.wdk import ColumnCounts, ColumnNotCountedError, CountedValue

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.column_reads import ColumnSite, serve_columns
from pathfinder.tests._support.recorded_columns import column_catalog
from pathfinder.tests._support.step_tally_site import TallySite, ToolServer, serve
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead._site_verdict import (
    UNANSWERED_DIGEST,
    VALID,
    serve_the_site,
    verify,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

pytestmark = pytest.mark.usefixtures("collector")

_PF = "Plasmodium falciparum 3D7"
_PF_IT = "Plasmodium falciparum IT"
_EXPORTED = 441126163
_EXPORTED_STRATEGY = 330125410


def _exported_deps() -> LeadDeps:
    organism = {"organism": MultiPickValue(values=[_PF])}
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("graph-1", "Exported", "plasmodb")
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(
            id="c_text",
            kind=StepKind.SEARCH,
            search_name="GenesByText",
            parameters={**organism, "text_expression": StringValue(value="PHIST")},
            record_class="transcript",
            display_name="Text",
        ),
    )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={"c_text": _EXPORTED},
        step_counts={"c_text": 4200},
        wdk_strategy_id=_EXPORTED_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_EXPORTED),
    )
    state = pipeline_state("plasmodb", user_prompt=f"PHIST genes of {_PF}")
    state.domain.operational_spec = OperationalSpec(
        goal="PHIST genes",
        criteria=[
            Criterion(
                id="c_text",
                text="PHIST genes",
                search_name="GenesByText",
                record_class="transcript",
                organism_param="organism",
                resolved_params=bound(
                    {**organism, "text_expression": StringValue(value="PHIST")}
                ),
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c_text")),
    )
    state.domain.requirements = [requirement(ConstraintKind.ORGANISM, "organism", _PF)]
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["c_text"], wdk_strategy_id=_EXPORTED_STRATEGY
    )
    return lead_deps(state, strategy_session=session)


def _exported_details() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _EXPORTED_STRATEGY,
            "name": "Exported",
            "rootStepId": _EXPORTED,
            "stepTree": {"stepId": _EXPORTED},
            "steps": {
                str(_EXPORTED): {
                    "id": _EXPORTED,
                    "searchName": "GenesByText",
                    "searchConfig": {
                        "parameters": {
                            "organism": f'["{_PF}"]',
                            "text_expression": "PHIST",
                        }
                    },
                    "recordClassName": "transcript",
                    "estimatedSize": 4200,
                    "validation": VALID,
                }
            },
        }
    )


def _organisms(*counted: tuple[str, int]) -> ColumnCounts:
    return ColumnCounts(
        step_id=_EXPORTED,
        column="organism",
        display_name="Organism",
        kind="string",
        total_records=sum(count for _, count in counted),
        distinct_values=len(counted),
        values=tuple(CountedValue(value=v, count=n) for v, n in counted),
    )


async def test_a_step_whose_organism_column_holds_a_second_organism_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _exported_details(), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    server = ToolServer(
        counts=_organisms(
            ("<i>Plasmodium falciparum</i> 3D7", 4179),
            ("<i>Plasmodium falciparum</i> IT", 21),
        )
    )
    serve(monkeypatch, TallySite(column_catalog(), step_count=4200), server)

    delta = await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)

    organism = SiteCheck(
        kind=ConstraintKind.ORGANISM,
        subject=_PF,
        status="fail",
        evidence=(
            f"21 of the 4,200 records of step {_EXPORTED} ('Text') hold organisms the "
            f"strategy does not select: {_PF_IT} (21)"
        ),
        requirement=f"organism:{_PF}",
    )
    assert server.counted == [("plasmodb", _EXPORTED, "organism", 200)]
    assert (delta.digest.success, delta.digest.gaps) == (
        False,
        [SiteCheckGap(check=organism)],
    )


async def test_an_organism_column_the_site_does_not_count_leaves_it_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _exported_details(), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    refused = ColumnNotCountedError(_EXPORTED, "organism", None, ("gene_type",))
    serve(
        monkeypatch,
        TallySite(column_catalog(), step_count=4200),
        ToolServer(refusal=refused),
    )

    delta = await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)

    [organism] = [c for c in delta.digest.review.checks if c.kind == "organism"]
    assert (delta.digest.success, organism.status) == (True, "unchecked")
    assert organism.evidence.startswith(
        f"the site does not count the organisms of step {_EXPORTED} ('Text'): "
    )


async def test_a_step_that_holds_only_the_selected_organism_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _exported_details(), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    serve(
        monkeypatch,
        TallySite(column_catalog(), step_count=4200),
        ToolServer(counts=_organisms(("<i>Plasmodium falciparum</i> 3D7", 4200))),
    )

    delta = await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)

    [organism] = [c for c in delta.digest.review.checks if c.kind == "organism"]
    assert (delta.digest.success, organism.status, organism.evidence) == (
        True,
        "pass",
        (
            f"all 4,200 records of step {_EXPORTED} ('Text') hold an organism the "
            f"strategy selects: {_PF} (4,200)"
        ),
    )
