"""The edit dispatch: misrouted edits, and the snapshot it emits."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.domain.parameters.values import MultiPickValue
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="proteases",
        criteria=[
            Criterion(
                id="step_text",
                text="protease text",
                search_name="GenesByText",
                role="seed",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            ),
            Criterion(id="step_go", text="proteolysis GO", search_name="GenesByGoTerm"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(kind="leaf", criterion_id="step_go"),
                ],
            )
        ),
    )


async def test_an_edit_on_a_thread_with_no_strategy_keeps_the_framed_spec() -> None:
    """A misrouted edit is a retry, and it destroys nothing the turn framed."""
    deps = lead_deps(
        pipeline_state(
            user_prompt="use P. vivax for the GO criterion",
            domain=StrategyDomainState(operational_spec=_spec()),
        ),
    )
    deps.state.domain.spec_before_turn = None

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=deps, parent_tool_call_id="t1", reason="edit it")

    assert "frame_problem" in str(excinfo.value)
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {"step_text", "step_go"}


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: calls.append)
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("graph-1", "Heat shock", "plasmodb"))
    edit_dispatch._emit_graph_snapshot(
        AgentDeps(site_id="plasmodb", strategy_session=session)
    )
    return calls


def test_the_snapshot_reaches_the_writer_under_the_chunk_key(
    emitted: list[dict[str, Any]],
) -> None:
    assert [call["chunk"]["type"] for call in emitted] == ["data-graph-snapshot"]


def test_the_envelope_omits_the_keys_the_chunk_leaves_unset(
    emitted: list[dict[str, Any]],
) -> None:
    """``DataChunk`` declares optional ``id`` and ``transient`` keys, and every
    emitted chunk is persisted verbatim."""
    assert sorted(emitted[0]["chunk"]) == ["data", "type"]


def test_the_snapshot_payload_names_the_graph(
    emitted: list[dict[str, Any]],
) -> None:
    assert emitted[0]["chunk"]["data"]["strategyId"] == "graph-1"
