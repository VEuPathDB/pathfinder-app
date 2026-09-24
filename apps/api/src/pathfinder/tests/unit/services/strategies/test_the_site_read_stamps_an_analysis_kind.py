"""A step the researcher adds on VEuPathDB takes its analysis kind from the catalog."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree, walk
from veupathdb.wdk import StrategyAPI, WDKStepTree, WDKStrategyDetails
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.strategies import site_changes
from pathfinder.services.strategies.site_changes import take_what_the_site_holds
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.analysis_catalog import (
    DESEQ_SEARCH,
    serve_the_catalog,
)
from pathfinder.tests.unit.ai.lead._analysis_thread import document

_TAXON = "step_taxon"
_TAXON_WDK = 440537300
_DESEQ_WDK = 440537301
_COMBINE_WDK = 440537302
_DATASET = "DS_e973eadd57"


def _graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "DESeq", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id=_TAXON,
            search_name="GenesByTaxon",
            parameters={"organism": StringValue(value="Pf3D7")},
        )
    )
    graph.recompute_roots()
    return graph


def _site() -> WDKStrategyDetails:
    """The site holding the thread's step and a DESeq step the researcher added."""
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330679883,
            "name": "DESeq",
            "rootStepId": _COMBINE_WDK,
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "stepTree": {
                "stepId": _COMBINE_WDK,
                "primaryInput": {"stepId": _TAXON_WDK},
                "secondaryInput": {"stepId": _DESEQ_WDK},
            },
            "steps": {
                str(_TAXON_WDK): {
                    "id": _TAXON_WDK,
                    "searchName": "GenesByTaxon",
                    "searchConfig": {"parameters": {"organism": "Pf3D7"}},
                },
                str(_DESEQ_WDK): {
                    "id": _DESEQ_WDK,
                    "searchName": DESEQ_SEARCH,
                    "searchConfig": {
                        "parameters": {
                            EDA_DATASET_ID_PARAM: _DATASET,
                            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05).value,
                        }
                    },
                },
                str(_COMBINE_WDK): {
                    "id": _COMBINE_WDK,
                    "searchName": "boolean_question_transcript",
                    "searchConfig": {"parameters": {"bq_operator": "INTERSECT"}},
                },
            },
        }
    )


async def _as_strings(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, dict[str, str]]
) -> None:
    del api
    for node in walk(payload.root):
        if node.id in wire:
            node.parameters = {
                name: StringValue(value=value) for name, value in wire[node.id].items()
            }


async def test_a_step_added_on_the_site_takes_its_kind_from_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = serve_the_catalog(monkeypatch)
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _as_strings)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)
    graph = _graph()

    edits = await take_what_the_site_holds(
        graph=graph,
        sync_state=WDKSyncState(
            wdk_step_ids={_TAXON: _TAXON_WDK},
            wdk_strategy_id=330679883,
            wdk_step_tree=WDKStepTree(step_id=_TAXON_WDK),
        ),
        site_id="plasmodb",
        live=_site(),
    )

    assert edits.reshaped is True
    assert graph.analysis_kinds == {
        str(_DESEQ_WDK): StampedKind(
            search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE
        )
    }
    assert read == [DESEQ_SEARCH]
