"""A saved gene set reads its ids and its genes from the strategy's step."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.errors import ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.tools.standalone import workbench
from pathfinder.ai.tools.standalone.workbench_models import GeneSetCreatedResponse
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

SET_NAME = "gametocyte secreted candidates v3"
LEAF_STEP_ID = "step_leaf"
OTHER_LEAF_STEP_ID = "step_expression"
ROOT_STEP_ID = "step_root"
WDK_LEAF_STEP_ID = 227253270
WDK_OTHER_LEAF_STEP_ID = 227253280
WDK_ROOT_STEP_ID = 227253290
WDK_STRATEGY_ID = 214618620
STEP_GENES = ["PF3D7_0709000", "PF3D7_1133400", "PF3D7_1222600"]
PASTED_GENES = ["PF3D7_0102900", "PF3D7_0304600"]
# The step carries a hidden WDK default beside the value the researcher chose.
LEAF_PARAMS = {
    "text_expression": StringValue(value="secreted"),
    "dataset_url": StringValue(value="https://plasmodb.org/a/app/record/dataset/DS_1"),
}
VISIBLE_LEAF_PARAMS = {"text_expression": StringValue(value="secreted")}


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[GeneSet]:
    kept: list[GeneSet] = []
    monkeypatch.setattr(workbench, "save_gene_set", kept.append)
    return kept


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    seen: list[tuple[str, int]] = []

    async def _read(site_id: str, step_id: int) -> list[str]:
        seen.append((site_id, step_id))
        return list(STEP_GENES)

    monkeypatch.setattr(workbench, "step_gene_ids", _read)

    async def _visible(
        site_id: str, *, record_type: str, search_name: str
    ) -> frozenset[str]:
        del site_id, record_type, search_name
        return frozenset({"text_expression"})

    monkeypatch.setattr(workbench, "visible_parameter_names", _visible)
    return seen


def _leaf_node() -> StrategyStepNode:
    return StrategyStepNode(
        id=LEAF_STEP_ID,
        search_name="GenesByText",
        parameters=dict(LEAF_PARAMS),
    )


def _session_with(
    root: StrategyStepNode, wdk_step_ids: dict[str, int]
) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Secreted", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session.graph = graph
    sync_state = ensure_sync_state(session)
    sync_state.wdk_step_ids = dict(wdk_step_ids)
    sync_state.wdk_strategy_id = WDK_STRATEGY_ID
    return session


def _leaf_session() -> StrategySession:
    return _session_with(_leaf_node(), {LEAF_STEP_ID: WDK_LEAF_STEP_ID})


def _combine_session(
    root_search_name: str = COMBINE_SEARCH_NAME,
) -> StrategySession:
    root = StrategyStepNode(
        id=ROOT_STEP_ID,
        search_name=root_search_name,
        operator=CombineOp.INTERSECT,
        primary_input=_leaf_node(),
        secondary_input=StrategyStepNode(
            id=OTHER_LEAF_STEP_ID,
            search_name="GenesByRNASeq",
        ),
    )
    return _session_with(
        root,
        {
            ROOT_STEP_ID: WDK_ROOT_STEP_ID,
            LEAF_STEP_ID: WDK_LEAF_STEP_ID,
            OTHER_LEAF_STEP_ID: WDK_OTHER_LEAF_STEP_ID,
        },
    )


def _deps(session: StrategySession | None = None) -> AgentDeps:
    return agent_deps_for(
        lead_deps(
            pipeline_state(user_prompt=f"save these genes as {SET_NAME}"),
            strategy_session=session,
        )
    )


async def _save(
    deps: AgentDeps,
    *,
    step_id: str | None = None,
    gene_ids: list[str] | None = None,
) -> GeneSetCreatedResponse:
    result = await workbench.create_workbench_gene_set(
        run_context_for(deps, "call_save"),
        name=SET_NAME,
        step_id=step_id,
        gene_ids=gene_ids,
    )
    created = result.return_value
    assert isinstance(created, GeneSetCreatedResponse)
    return created


async def test_a_save_from_a_leaf_step_reads_that_steps_genes(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    deps = _deps(_leaf_session())

    created = await _save(deps, step_id=LEAF_STEP_ID)

    assert reads == [("plasmodb", WDK_LEAF_STEP_ID)]
    assert saved[0].gene_ids == STEP_GENES
    assert (saved[0].wdk_step_id, saved[0].wdk_strategy_id) == (
        WDK_LEAF_STEP_ID,
        WDK_STRATEGY_ID,
    )
    assert saved[0].source == "strategy"
    assert saved[0].search_name == "GenesByText"
    assert saved[0].parameters == VISIBLE_LEAF_PARAMS
    assert created.gene_set_created.gene_count == 3


async def test_a_save_that_names_no_step_reads_the_root(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    """The root is a combine, so the set records the step and no search."""
    deps = _deps(_combine_session())

    await _save(deps)

    assert reads == [("plasmodb", WDK_ROOT_STEP_ID)]
    assert saved[0].gene_ids == STEP_GENES
    assert saved[0].wdk_step_id == WDK_ROOT_STEP_ID
    assert saved[0].source == "strategy"
    assert saved[0].search_name is None
    assert saved[0].parameters is None


async def test_a_combine_named_by_its_wdk_question_records_no_search(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    """A synced combine carries WDK's boolean question name; it is still no search."""
    deps = _deps(
        _combine_session(
            "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"
        )
    )

    await _save(deps)

    assert reads == [("plasmodb", WDK_ROOT_STEP_ID)]
    assert saved[0].wdk_step_id == WDK_ROOT_STEP_ID
    assert saved[0].search_name is None
    assert saved[0].parameters is None


async def test_a_transform_root_records_no_search(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    """A transform cannot be re-run from its parameters alone, so none is recorded."""
    root = StrategyStepNode(
        id=ROOT_STEP_ID,
        search_name="GenesByOrthologs",
        parameters={"organism": StringValue(value="Plasmodium vivax")},
        primary_input=_leaf_node(),
    )
    deps = _deps(
        _session_with(
            root, {ROOT_STEP_ID: WDK_ROOT_STEP_ID, LEAF_STEP_ID: WDK_LEAF_STEP_ID}
        )
    )

    await _save(deps)

    assert reads == [("plasmodb", WDK_ROOT_STEP_ID)]
    assert saved[0].wdk_step_id == WDK_ROOT_STEP_ID
    assert saved[0].search_name is None
    assert saved[0].parameters is None


async def test_a_pasted_list_is_saved_as_a_list(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    """A list the model holds is never stamped with a step it did not read."""
    deps = _deps(_combine_session())

    created = await _save(deps, gene_ids=PASTED_GENES)

    assert reads == []
    assert saved[0].gene_ids == PASTED_GENES
    assert (saved[0].wdk_step_id, saved[0].wdk_strategy_id) == (None, None)
    assert (saved[0].search_name, saved[0].parameters) == (None, None)
    assert saved[0].source == "paste"
    assert "no pushed strategy step" in created.message


async def test_a_pasted_list_with_a_step_is_refused(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    deps = _deps(_leaf_session())

    with pytest.raises(ModelRetry) as raised:
        await _save(deps, gene_ids=PASTED_GENES, step_id=LEAF_STEP_ID)

    assert "carries no strategy step" in str(raised.value)
    assert (saved, reads) == ([], [])


async def test_a_thread_with_no_pushed_strategy_is_refused(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    deps = _deps()

    with pytest.raises(ModelRetry) as raised:
        await _save(deps)

    assert "no pushed strategy step to save from" in str(raised.value)
    assert (saved, reads) == ([], [])


async def test_a_step_the_strategy_does_not_hold_is_refused(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    deps = _deps(_leaf_session())

    with pytest.raises(ModelRetry) as raised:
        await _save(deps, step_id="step_999")

    assert LEAF_STEP_ID in str(raised.value)
    assert (saved, reads) == ([], [])


async def test_a_step_that_returns_no_genes_is_refused(
    saved: list[GeneSet], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _empty(site_id: str, step_id: int) -> list[str]:
        del site_id, step_id
        return []

    monkeypatch.setattr(workbench, "step_gene_ids", _empty)
    deps = _deps(_leaf_session())

    with pytest.raises(ModelRetry) as raised:
        await _save(deps, step_id=LEAF_STEP_ID)

    assert "no genes" in str(raised.value)
    assert saved == []


async def test_a_save_keeps_the_parameters_a_user_sees_and_drops_the_hidden_ones(
    saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    """WDK fills a hidden parameter itself; it is no choice the researcher made."""
    del reads

    await _save(_deps(_leaf_session()), step_id=LEAF_STEP_ID)

    assert saved[0].parameters == VISIBLE_LEAF_PARAMS


async def test_a_search_the_catalog_cannot_read_still_saves_the_set(
    monkeypatch: pytest.MonkeyPatch, saved: list[GeneSet], reads: list[tuple[str, int]]
) -> None:
    """The genes are already in hand, so a definition nobody can read loses nothing."""
    del reads

    async def _unreadable(
        site_id: str, *, record_type: str, search_name: str
    ) -> frozenset[str]:
        del site_id, record_type
        raise ValidationError(
            title="Search definition could not be read", detail=search_name
        )

    monkeypatch.setattr(workbench, "visible_parameter_names", _unreadable)

    await _save(_deps(_leaf_session()), step_id=LEAF_STEP_ID)

    assert saved[0].parameters == LEAF_PARAMS
