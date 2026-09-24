"""A step a build mints under a new id takes its analysis kind in the same turn.

A build after a clear, and the clone a saved strategy's insert pushes, both
write steps no stored kind names; the build reads each from the catalog.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    walk,
)
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails
from veupathdb_mcp.catalog import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
)

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_tree import (
    build_step_tree,
)
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.services.eda.export import exported_analysis
from pathfinder.services.strategies import insert_saved
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.insert_saved import insert_saved_into_conversation
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.tests._support.analysis_catalog import DESEQ_SEARCH, serve_the_catalog
from pathfinder.tests.unit.ai.lead._analysis_thread import document
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api

_DATASET = "DS_e973eadd57"


def _params() -> dict[str, StringValue]:
    return {
        EDA_DATASET_ID_PARAM: StringValue(value=_DATASET),
        EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
    }


def _session(*roots: StrategyStepNode) -> StrategySession:
    graph = StrategyGraph("g1", "DE", "plasmodb")
    graph.record_type = "transcript"
    for root in roots:
        graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    return session


def _stored_kinds(session: StrategySession) -> dict[str, StampedKind]:
    graph = session.get_graph(None)
    assert graph is not None
    ast = graph.to_strategy_ast()
    assert ast is not None
    return StepWords.of(ast).analysis_kinds


async def test_a_build_after_a_clear_gives_the_minted_step_its_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan holds the export's criterion; the build mints its step anew."""
    install_stub_api(monkeypatch)
    read = serve_the_catalog(monkeypatch)
    binding = exported_analysis(AnalysisKind.COMPUTE, _params())
    assert binding is not None
    built = build_step_tree(
        OperationalSpec(
            criteria=[
                Criterion(
                    id="step_x",
                    text="up at 24h",
                    search_name=COMPUTE_QUERY,
                    analysis=binding,
                )
            ],
            structure=SpecStructure(
                root=StructureNode(kind="leaf", criterion_id="step_x")
            ),
        )
    )
    session = _session()

    await build_strategy_from_spec(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        root=built.root,
    )

    minted = built.step_id_by_criterion["step_x"]
    assert _stored_kinds(session) == {
        minted: StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }
    assert read == [COMPUTE_QUERY]


def _saved_on_the_site() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 7777,
            "name": "Saved DESeq",
            "rootStepId": 1,
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "stepTree": {"stepId": 1},
            "steps": {
                "1": {
                    "id": 1,
                    "searchName": DESEQ_SEARCH,
                    "searchConfig": {
                        "parameters": {
                            EDA_DATASET_ID_PARAM: _DATASET,
                            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05).value,
                        }
                    },
                }
            },
        }
    )


class _SavedSite:
    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del strategy_id, user_id
        return _saved_on_the_site()


async def _as_strings(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, dict[str, str]]
) -> None:
    del api
    for node in walk(payload.root):
        node.parameters = {
            name: StringValue(value=value) for name, value in wire[node.id].items()
        }


async def _nothing(**_kwargs: object) -> None:
    return None


async def test_an_inserted_saved_deseq_step_takes_its_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    serve_the_catalog(monkeypatch)
    site: Any = _SavedSite()
    monkeypatch.setattr(insert_saved, "get_strategy_api", lambda _site: site)
    monkeypatch.setattr(insert_saved, "canonicalize_synced_parameters", _as_strings)
    monkeypatch.setattr(insert_saved, "_record_consumer", _nothing)
    session = _session(
        StrategyStepNode(
            id="step_a",
            search_name="GenesByGoTerm",
            parameters={"go_term": StringValue(value="GO:0004672")},
        )
    )

    await insert_saved_into_conversation(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        target_step_id="step_a",
        saved_wdk_strategy_id=7777,
        operator=CombineOp.INTERSECT,
    )

    graph = session.get_graph(None)
    assert graph is not None
    [inserted] = [s.id for s in graph.steps.values() if s.search_name == DESEQ_SEARCH]
    assert _stored_kinds(session) == {
        inserted: StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)
    }
