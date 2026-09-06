"""The pinned instructions a strategy builder renders: workspace, graph, ledger."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import MagicMock

import pytest
from veupathdb.domain.parameters.values import (
    MultiPickValue,
    NumberValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession

from pathfinder.ai.agents.strategy_instructions import (
    pinned_frame_workspace,
    pinned_graph_state,
    pinned_ledger,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.fixtures.builders import add_step_to_graph


def _ctx(spec: OperationalSpec) -> Any:
    ctx = MagicMock()
    ctx.deps = MagicMock()
    ctx.deps.agent_state.operational_spec_draft = spec
    return ctx


def _bound_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="find kinases",
        criteria=[
            Criterion(
                id="c_expr",
                text="genes in the top decile of expression",
                search_name="GenesByRNASeqEvidence",
                resolved_params={
                    "min_expression_percentile": NumberValue(value=90),
                    "any_or_all": SinglePickValue(value="any"),
                    "organism": MultiPickValue(values=["Plasmodium"]),
                },
            )
        ],
    )


def test_workspace_renders_bound_values() -> None:
    rendered = pinned_frame_workspace(_ctx(_bound_spec()))

    assert rendered is not None
    assert "min_expression_percentile=90" in rendered


def test_workspace_renders_a_multi_pick_in_wire_form() -> None:
    rendered = pinned_frame_workspace(_ctx(_bound_spec()))

    assert rendered is not None
    assert 'organism=["Plasmodium"]' in rendered
    assert "any_or_all=any" in rendered


def test_workspace_says_the_values_are_preserved_unless_the_request_changes_them() -> (
    None
):
    rendered = pinned_frame_workspace(_ctx(_bound_spec()))

    assert rendered is not None
    assert "preserved unless the request changes them" in rendered


def test_workspace_still_names_the_open_slots() -> None:
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(
                id="c_open",
                text="a criterion with an unanswered parameter",
                search_name="GenesByRNASeqEvidence",
                open_params=[OpenSlot(criterion_id="c_open", param_name="profileset")],
            )
        ],
    )

    rendered = pinned_frame_workspace(_ctx(spec))

    assert rendered is not None
    assert "profileset" in rendered


def test_an_empty_draft_renders_nothing() -> None:
    empty = pinned_frame_workspace(_ctx(OperationalSpec(goal="g")))
    bound = pinned_frame_workspace(_ctx(_bound_spec()))
    assert (empty, bound is None) == (None, False)


def _ledger_ctx(ledger_summary: str) -> Any:
    ctx = MagicMock()
    ctx.deps = MagicMock()
    ctx.deps.ledger_summary = ledger_summary
    return ctx


def test_pinned_ledger_renders_summary() -> None:
    rendered = pinned_ledger(
        _ledger_ctx("## Frame\n- present: True\n## Discovery\n- selected: 0")
    )
    assert rendered is not None
    assert "Frame" in rendered
    assert "Discovery" in rendered


def test_pinned_ledger_none_when_empty() -> None:
    empty = pinned_ledger(_ledger_ctx(""))
    filled = pinned_ledger(_ledger_ctx("## Frame\n- present: True"))
    assert (empty, filled is None) == (None, False)


def _graph_ctx(session: StrategySession) -> Any:
    ctx = MagicMock()
    ctx.deps = MagicMock()
    ctx.deps.strategy_session = session
    return ctx


def _session(graph: StrategyGraph, sync: WDKSyncState | None = None) -> StrategySession:
    session = StrategySession("plasmodb")
    session.add_graph(graph)
    if sync is not None:
        session.sync_state = sync
    return session


def _graph_with_a_combine() -> StrategyGraph:
    graph = StrategyGraph("g1", "kinases", "plasmodb")
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(
            id="a",
            kind=StepKind.SEARCH,
            search_name="GenesByText",
            display_name="kinase text",
            parameters={"text_expression": StringValue(value="kinase")},
        ),
    )
    add_step_to_graph(
        graph,
        StrategyStep(
            id="b",
            kind=StepKind.SEARCH,
            search_name="GenesByMolecularWeight",
            parameters={"min_molecular_weight": NumberValue(value=1000)},
        ),
    )
    add_step_to_graph(
        graph,
        StrategyStep(
            id="c",
            kind=StepKind.COMBINE,
            primary_input_id="a",
            secondary_input_id="b",
            operator=CombineOp.INTERSECT,
        ),
    )
    return graph


class TestTheRenderedGraph:
    def test_an_empty_thread_and_an_empty_graph_render_nothing(self) -> None:
        empty_thread = pinned_graph_state(_graph_ctx(StrategySession("plasmodb")))
        empty_graph = pinned_graph_state(
            _graph_ctx(_session(StrategyGraph("g1", "kinases", "plasmodb")))
        )

        assert (empty_thread, empty_graph) == (None, None)

    def test_a_leaf_names_its_search_and_its_parameters(self) -> None:
        rendered = pinned_graph_state(_graph_ctx(_session(_graph_with_a_combine())))

        assert rendered is not None
        assert "a: GenesByText [leaf]" in rendered
        assert '"kinase text"' in rendered
        assert "text_expression=kinase" in rendered

    def test_a_combine_names_its_operator_and_both_inputs(self) -> None:
        rendered = pinned_graph_state(_graph_ctx(_session(_graph_with_a_combine())))

        assert rendered is not None
        assert "c: INTERSECT(a, b)" in rendered

    def test_a_combine_carries_no_parameter_line(self) -> None:
        rendered = pinned_graph_state(_graph_ctx(_session(_graph_with_a_combine())))

        assert rendered is not None
        combine_line = next(
            line for line in rendered.splitlines() if line.startswith("c:")
        )
        assert "=" not in combine_line

    def test_the_header_counts_the_steps(self) -> None:
        rendered = pinned_graph_state(_graph_ctx(_session(_graph_with_a_combine())))

        assert rendered is not None
        assert rendered.startswith("Current strategy graph (3 steps):")

    def test_the_counts_and_the_wdk_ids_ride_each_step(self) -> None:
        sync = WDKSyncState()
        sync.step_counts["a"] = 12345
        sync.wdk_step_ids["a"] = 999
        sync.wdk_strategy_id = 4242

        rendered = pinned_graph_state(
            _graph_ctx(_session(_graph_with_a_combine(), sync))
        )

        assert rendered is not None
        assert "wdk_strategy=4242" in rendered
        assert "12,345 genes" in rendered
        assert "wdk=999" in rendered

    def test_a_push_error_is_reported_on_its_step(self) -> None:
        sync = WDKSyncState()
        sync.wdk_push_errors["b"] = "422 unprocessable"

        rendered = pinned_graph_state(
            _graph_ctx(_session(_graph_with_a_combine(), sync))
        )

        assert rendered is not None
        assert "ERROR: 422 unprocessable" in rendered


def test_the_context_package_is_gone() -> None:
    """The one live renderer moved here; nothing else in the package was used."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pathfinder.ai.context")
