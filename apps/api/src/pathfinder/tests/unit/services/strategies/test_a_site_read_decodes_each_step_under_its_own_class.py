from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue, ParamValue
from veupathdb.domain.strategy import (
    CombineOp,
    StepValidation,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import (
    WDKNumberParam,
    WDKSearch,
    WDKSearchResponse,
    WDKStepTree,
    WDKStrategyDetails,
)

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import site_changes
from pathfinder.services.strategies.site_changes import (
    SiteEdits,
    take_what_the_site_holds,
)
from pathfinder.services.strategies.sync_state import WDKSyncState

_PARAMETER_OF = {
    "SnpsByLocation": "start_point",
    "GenesByMolecularWeight": "min_molecular_weight",
    "GenesByRetiredScore": "min_score",
}


@dataclass
class _SearchSpecs:
    reads: list[tuple[str, str]] = field(default_factory=list)

    def _response(self, search_name: str) -> WDKSearchResponse:
        return WDKSearchResponse(
            search_data=WDKSearch(
                url_segment=search_name,
                parameters=[WDKNumberParam(name=_PARAMETER_OF[search_name])],
            ),
            validation=StepValidation(level="NONE", is_valid=False),
        )

    async def get_search_details(
        self, record_type: str, search_name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del expand_params
        self.reads.append((record_type, search_name))
        return self._response(search_name)

    async def get_search_details_with_params(
        self,
        _record_type: str,
        search_name: str,
        context: dict[str, str],
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        del context, expand_params
        return self._response(search_name)


@dataclass
class _Site:
    client: _SearchSpecs = field(default_factory=_SearchSpecs)


def _step(
    wdk_id: int, search_name: str, record_class: str | None, **wire: str
) -> dict[str, Any]:
    return {
        "id": wdk_id,
        "searchName": search_name,
        "searchConfig": {"parameters": wire},
        "recordClassName": record_class,
    }


def _live(tree: dict[str, Any], *steps: dict[str, Any]) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330534200,
            "name": "genes near snps",
            "rootStepId": tree["stepId"],
            "recordClassName": "transcript",
            "stepTree": tree,
            "steps": {str(step["id"]): step for step in steps},
        }
    )


def _genes_from_snps() -> StrategyGraph:
    graph = StrategyGraph("g1", "genes near snps", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_genes",
            search_name="GenesBySnps",
            primary_input=StrategyStepNode(
                id="step_snps",
                search_name="SnpsByLocation",
                parameters={"start_point": NumberValue(value=1000)},
            ),
        )
    )
    graph.recompute_roots()
    return graph


def _held(held: dict[str, int], tree: WDKStepTree) -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids=held, wdk_strategy_id=330534200, wdk_step_tree=tree
    )


async def _read(
    monkeypatch: pytest.MonkeyPatch,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    live: WDKStrategyDetails,
) -> tuple[SiteEdits, list[tuple[str, str]]]:
    site = _Site()
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site_id: site)
    edits = await take_what_the_site_holds(
        graph=graph, sync_state=sync_state, site_id="plasmodb", live=live
    )
    return edits, site.client.reads


_SNPS_UNDER_GENES = {"stepId": 501, "primaryInput": {"stepId": 502}}


async def test_a_snp_leaf_under_a_gene_root_is_decoded_under_snp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _genes_from_snps()
    live = _live(
        _SNPS_UNDER_GENES,
        _step(501, "GenesBySnps", "transcript"),
        _step(502, "SnpsByLocation", "snp", start_point="2000"),
    )
    held = _held({"step_genes": 501, "step_snps": 502}, live.step_tree)

    edits, reads = await _read(monkeypatch, graph, held, live)

    assert (edits.valued, reads) == (["step_snps"], [("snp", "SnpsByLocation")])
    assert graph.steps["step_snps"].parameters == {
        "start_point": NumberValue(value=2000)
    }


@pytest.mark.parametrize(
    ("record_class", "wire", "reads", "decoded"),
    [
        (
            "snp",
            {"start_point": "3000"},
            [("snp", "SnpsByLocation")],
            {"start_point": NumberValue(value=3000)},
        ),
        ("snp", {}, [], {}),
        (None, {"start_point": "3000"}, [], {}),
    ],
)
async def test_a_leaf_the_site_added_under_a_gene_root_is_taken(
    monkeypatch: pytest.MonkeyPatch,
    record_class: str | None,
    wire: dict[str, str],
    reads: list[tuple[str, str]],
    decoded: dict[str, ParamValue],
) -> None:
    graph = _genes_from_snps()
    held = _held(
        {"step_genes": 501, "step_snps": 502},
        WDKStepTree.model_validate(_SNPS_UNDER_GENES),
    )
    live = _live(
        {"stepId": 501, "primaryInput": {"stepId": 503}},
        _step(501, "GenesBySnps", "transcript"),
        _step(503, "SnpsByLocation", record_class, **wire),
    )

    edits, read = await _read(monkeypatch, graph, held, live)

    assert (edits.reshaped, read, sorted(graph.steps)) == (
        True,
        reads,
        ["503", "step_genes"],
    )
    assert graph.steps["503"].parameters == decoded


async def test_a_retired_leaf_with_no_class_keeps_its_values_and_the_rest_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retired: dict[str, ParamValue] = {"min_score": NumberValue(value=5)}
    graph = StrategyGraph("g1", "heavy scored genes", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_both",
            search_name="boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="step_retired",
                search_name="GenesByRetiredScore",
                parameters=retired,
            ),
            secondary_input=StrategyStepNode(
                id="step_weight",
                search_name="GenesByMolecularWeight",
                parameters={"min_molecular_weight": NumberValue(value=10000)},
            ),
        )
    )
    graph.recompute_roots()
    live = _live(
        {
            "stepId": 600,
            "primaryInput": {"stepId": 601},
            "secondaryInput": {"stepId": 602},
        },
        _step(
            600,
            "boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
            "transcript",
            bq_operator="INTERSECT",
        ),
        _step(601, "GenesByRetiredScore", None, min_score="9"),
        _step(
            602, "GenesByMolecularWeight", "transcript", min_molecular_weight="20000"
        ),
    )
    held = _held(
        {"step_both": 600, "step_retired": 601, "step_weight": 602},
        live.step_tree,
    )

    edits, reads = await _read(monkeypatch, graph, held, live)

    assert (edits.valued, reads) == (
        ["step_weight"],
        [("transcript", "GenesByMolecularWeight")],
    )
    assert (
        graph.steps["step_retired"].parameters,
        graph.steps["step_weight"].parameters,
    ) == (retired, {"min_molecular_weight": NumberValue(value=20000)})
