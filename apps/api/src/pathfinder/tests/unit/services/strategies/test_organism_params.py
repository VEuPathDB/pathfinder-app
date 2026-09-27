"""The parameter each search of a tree marks as its organism, read from the catalog."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.errors import WDKError

from pathfinder.services.strategies import organism_params, sync
from pathfinder.services.strategies.organism_params import tree_organism_parameters
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    leaf,
    session_with,
)

# The marks plasmodb publishes for the searches of the tree below.
_MARKS = {
    "GenesByNgsSnps": "organismSinglePick",
    "GenesWithSignalPeptide": "organism",
    "GenesByOrthologs": "organism",
}
_NO_SUCH_SEARCH = WDKError("no such search", status=404)


def _tree() -> StrategyStepNode:
    snps = StrategyStepNode(
        search_name="GenesByNgsSnps",
        parameters={"organismSinglePick": MultiPickValue(values=["P. falciparum"])},
    )
    signal = StrategyStepNode(search_name="GenesWithSignalPeptide")
    joined = StrategyStepNode(
        search_name="boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
        operator=CombineOp.INTERSECT,
        primary_input=snps,
        secondary_input=signal,
    )
    return StrategyStepNode(search_name="GenesByOrthologs", primary_input=joined)


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def _record_type(*_args: Any, **_kwargs: Any) -> str:
        return "transcript"

    async def _marked(_site: str, _record_type: str, search_name: str) -> str | None:
        asked.append(search_name)
        if search_name == "GenesByNothing":
            raise _NO_SUCH_SEARCH
        return _MARKS.get(search_name)

    monkeypatch.setattr(organism_params, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(organism_params, "organism_parameter", _marked)
    return asked


async def test_each_search_of_the_tree_names_its_marked_parameter(
    read: list[str],
) -> None:
    marks = await tree_organism_parameters("plasmodb", "transcript", _tree())

    assert marks == _MARKS
    assert sorted(read) == sorted(_MARKS)


async def test_a_search_the_catalog_cannot_read_names_none(read: list[str]) -> None:
    tree = StrategyStepNode(
        search_name="GenesByOrthologs",
        primary_input=StrategyStepNode(search_name="GenesByNothing"),
    )

    marks = await tree_organism_parameters("plasmodb", "transcript", tree)

    assert (marks, sorted(read)) == (
        {"GenesByOrthologs": "organism"},
        ["GenesByNothing", "GenesByOrthologs"],
    )


async def test_a_sync_records_the_marks_of_the_tree_it_pushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = StubAPI()
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site: api)
    ids = {"step_a": 440537303, "step_b": 440537313, "step_join": 440537323}
    session = session_with(combine("step_join", leaf("step_a"), leaf("step_b")), ids)
    assert session.graph is not None
    for step in session.graph.steps.values():
        step.record_class = "transcript"
    state = WDKSyncState(wdk_step_ids=dict(ids))

    await sync.sync_strategy_for_site(
        graph=session.graph, sync_state=state, site_id="plasmodb"
    )

    assert state.organism_params == {"GenesByTaxon": "organism"}
