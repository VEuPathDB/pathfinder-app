"""An EDA step's analysis kind travels with the stored strategy, as its words do.

A step imported from VEuPathDB carries none, so the import reads it from the
catalog; a re-import reads it again.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree, walk
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.operations.types import DuplicateStepOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.persistence.models import PersistedStrategyGraph
from pathfinder.services.strategies import wdk_sync
from pathfinder.services.strategies.commit import graph_labels, restore_graph
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.wdk_sync import fetch_and_convert
from pathfinder.tests._support.analysis_catalog import (
    DESEQ_SEARCH,
    serve_the_catalog,
)
from pathfinder.tests.unit.ai.lead._analysis_thread import document

_DATASET = "DS_e973eadd57"
_WDK_STEP = 440537300


def _deseq(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=DESEQ_SEARCH,
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET),
            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
        },
    )


def _graph_of(step_id: str) -> StrategyGraph:
    graph = StrategyGraph("g1", "DESeq", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(_deseq(step_id)))
    graph.recompute_roots()
    return graph


def test_a_graph_stores_the_kind_of_each_step_it_holds() -> None:
    graph = _graph_of("step_a")
    graph.note_analysis_kinds(
        {
            "step_a": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE),
            "step_gone": StampedKind(
                search_name=DESEQ_SEARCH, kind=AnalysisKind.SUBSET
            ),
        }
    )

    ast = graph.to_strategy_ast()

    assert ast is not None
    assert StepWords.of(ast).analysis_kinds == {
        "step_a": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)
    }


def test_a_loaded_strategy_holds_the_kinds_it_stored() -> None:
    stored = StrategyAst(
        record_type="transcript",
        root=_deseq("step_a"),
        metadata=StepWords(
            analysis_kinds={
                "step_a": StampedKind(
                    search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE
                )
            }
        ).model_dump(by_alias=True, mode="json"),
    )

    session = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id=str(uuid4()), name="DESeq", strategy_ast=stored
        ),
    )

    assert session.graph is not None
    assert session.graph.analysis_kinds == {
        "step_a": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)
    }


def test_a_rolled_back_batch_puts_the_kinds_back() -> None:
    graph = _graph_of("step_a")
    graph.note_analysis_kinds(
        {"step_a": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)}
    )
    entry = graph_labels(graph)
    old = graph.to_strategy_ast()

    graph.note_analysis_kinds(
        {"step_a": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.SUBSET)}
    )
    restore_graph(graph, old, entry)

    assert graph.analysis_kinds == {
        "step_a": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)
    }


def _on_the_site() -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330679883,
            "name": "DESeq",
            "rootStepId": _WDK_STEP,
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "stepTree": {"stepId": _WDK_STEP},
            "steps": {
                str(_WDK_STEP): {
                    "id": _WDK_STEP,
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


class _Site:
    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del strategy_id, user_id
        return _on_the_site()


async def _as_strings(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, dict[str, str]]
) -> None:
    """Decode every wire value as the string parameter it is."""
    del api
    for node in walk(payload.root):
        node.parameters = {
            name: StringValue(value=value) for name, value in wire[node.id].items()
        }


async def _imported(monkeypatch: pytest.MonkeyPatch) -> StrategyAst:
    monkeypatch.setattr(wdk_sync, "canonicalize_synced_parameters", _as_strings)
    site: Any = _Site()
    payload, _saved = await fetch_and_convert(site, 330679883, site_id="plasmodb")
    return payload


async def test_an_import_reads_each_kind_from_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = serve_the_catalog(monkeypatch)

    payload = await _imported(monkeypatch)

    assert StepWords.of(payload).analysis_kinds == {
        str(_WDK_STEP): StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)
    }
    assert read == [DESEQ_SEARCH]


async def test_a_re_import_carries_only_the_kinds_the_catalog_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The site's strategy replaces the stored one, so the words it stored are
    lost and each kind is read again."""
    serve_the_catalog(monkeypatch)
    await _imported(monkeypatch)

    again = await _imported(monkeypatch)

    assert StepWords.of(again) == StepWords(
        analysis_kinds={
            str(_WDK_STEP): StampedKind(
                search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE
            )
        }
    )


def test_a_duplicated_eda_step_carries_its_sources_kind() -> None:
    """The copy runs the same search on the same document, so no catalog read."""
    graph = _graph_of("step_de")
    graph.note_analysis_kinds(
        {"step_de": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)}
    )

    apply_operation(
        graph,
        DuplicateStepOp(
            source_step_id="step_de",
            duplicate_step_id="step_dup",
            combine_step_id="step_c",
        ),
    )

    ast = graph.to_strategy_ast()
    assert ast is not None
    assert StepWords.of(ast).analysis_kinds == {
        "step_de": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE),
        "step_dup": StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE),
    }
