"""Tests for the operation-based strategy edit tool.

An edit states the base revision it works from. The revision fingerprint covers
strategy inputs only, so a refreshed count does not read as an edit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

import pytest
from pydantic_ai import Tool
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.tools.standalone.strategy import apply_operations, build_strategy
from pathfinder.ai.tools.toolsets.execution import build_toolset
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operations import GraphOperation, UpdateStepMetaOp
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.operations import editable_models
from pathfinder.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
    leaf,
    pin_apply,
    revision_of,
)
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

Build = Callable[..., Awaitable[BuildOutcome]]


def _outcome() -> BuildOutcome:
    return BuildOutcome(wdk_strategy_id=1, root_count=0)


def _pin_build(monkeypatch: pytest.MonkeyPatch, build: Build) -> None:
    monkeypatch.setattr(
        "pathfinder.ai.tools.standalone.strategy.build_strategy_from_spec",
        build,
    )


class TestRevisionPrecondition:
    async def test_a_matching_revision_applies_the_operations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        await apply_operations(
            ctx,
            base_revision=revision_of(graph),
            operations=[UpdateStepMetaOp(step_id="step_a", display_name="Kinases")],
        )

        assert len(committed) == 1
        assert len(committed[0]) == 1

    async def test_a_stale_revision_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        with pytest.raises(ModelRetry):
            await apply_operations(
                ctx,
                base_revision="deadbeefdeadbeef",
                operations=[UpdateStepMetaOp(step_id="step_a", display_name="Kinases")],
            )

        assert committed == []

    async def test_the_refusal_carries_the_current_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal carries the current revision, so a retry needs no extra
        read."""
        graph = graph_with(leaf("step_a"))
        ctx, commit = context_and_commit(graph, [])
        pin_apply(monkeypatch, commit)

        with pytest.raises(ModelRetry) as caught:
            await apply_operations(
                ctx,
                base_revision="stale",
                operations=[UpdateStepMetaOp(step_id="step_a", display_name="x")],
            )

        assert revision_of(graph) in str(caught.value)

    async def test_a_human_edit_between_turns_blocks_the_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A parameter change between the read and the write blocks the
        write."""
        graph = graph_with(leaf("step_a"))
        seen_by_model = revision_of(graph)
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        graph.steps["step_a"].parameters = {
            "organism": StringValue(value="P. vivax P01")
        }

        with pytest.raises(ModelRetry):
            await apply_operations(
                ctx,
                base_revision=seen_by_model,
                operations=[UpdateStepMetaOp(step_id="step_a", display_name="Kinases")],
            )

        assert committed == []
        assert graph.steps["step_a"].parameters["organism"] == StringValue(
            value="P. vivax P01"
        )

    async def test_a_refreshed_count_is_not_treated_as_an_edit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The fingerprint excludes counts, so a fresh count keeps a held
        revision valid."""
        graph = graph_with(leaf("step_a"))
        before = revision_of(graph)
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        ctx.deps.strategy_session.sync_state = WDKSyncState(
            step_counts={"step_a": 412}, wdk_step_ids={"step_a": 100}
        )

        await apply_operations(
            ctx,
            base_revision=before,
            operations=[UpdateStepMetaOp(step_id="step_a", display_name="Kinases")],
        )

        assert len(committed) == 1

    async def test_an_empty_graph_has_the_empty_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        assert revision_of(graph) == ""

        with pytest.raises(ModelRetry):
            await apply_operations(
                ctx,
                base_revision="something",
                operations=[UpdateStepMetaOp(step_id="step_a", display_name="x")],
            )


class TestOperationListValidation:
    async def test_an_empty_operation_list_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        with pytest.raises(ModelRetry):
            await apply_operations(ctx, base_revision=revision_of(graph), operations=[])

        assert committed == []


class TestBuildStrategyNoLongerClobbersSilently:
    async def test_replacing_a_non_empty_strategy_needs_the_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A whole-graph replacement over an existing strategy needs the
        revision."""
        graph = graph_with(leaf("step_a"))
        ctx, _commit = context_and_commit(graph, [])
        built: list[dict[str, object]] = []

        async def _build(**kwargs: object) -> BuildOutcome:
            built.append(kwargs)
            msg = "build must not run"
            raise AssertionError(msg)

        _pin_build(monkeypatch, _build)

        with pytest.raises(ModelRetry):
            await build_strategy(ctx, root=leaf("step_b"))

        assert built == []

    async def test_the_conflict_points_at_the_cheaper_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        ctx, _commit = context_and_commit(graph, [])

        with pytest.raises(ModelRetry) as caught:
            await build_strategy(ctx, root=leaf("step_b"))

        assert "apply_operations" in str(caught.value)
        assert revision_of(graph) in str(caught.value)

    async def test_an_empty_strategy_needs_no_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A build over an empty strategy overwrites nothing."""
        graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
        ctx, _commit = context_and_commit(graph, [])
        built: list[dict[str, object]] = []

        async def _build(**kwargs: object) -> BuildOutcome:
            built.append(kwargs)
            return _outcome()

        _pin_build(monkeypatch, _build)

        await build_strategy(ctx, root=leaf("step_a"))

        assert len(built) == 1

    async def test_a_zero_gene_build_reports_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A strategy that returns no genes is the failure the reader must see."""
        graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
        ctx, _commit = context_and_commit(graph, [])

        async def _build(**kwargs: object) -> BuildOutcome:
            del kwargs
            return _outcome()

        _pin_build(monkeypatch, _build)

        returned = await build_strategy(ctx, root=leaf("step_a"))

        summaries = [
            (chunk.data["summary"], chunk.data["status"])
            for chunk in returned.metadata
            if isinstance(chunk, DataChunk) and chunk.type == "data-tool-summary"
        ]
        assert summaries == [("0 steps, 0 records", "empty")]

    async def test_a_build_nobody_measured_says_the_count_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A root whose push failed carries no number, so the build reports none."""
        graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
        ctx, _commit = context_and_commit(graph, [])

        async def _build(**kwargs: object) -> BuildOutcome:
            del kwargs
            return BuildOutcome(wdk_strategy_id=1, root_count=None)

        _pin_build(monkeypatch, _build)

        returned = await build_strategy(ctx, root=leaf("step_a"))

        summaries = [
            (chunk.data["summary"], chunk.data["status"])
            for chunk in returned.metadata
            if isinstance(chunk, DataChunk) and chunk.type == "data-tool-summary"
        ]
        assert summaries == [("0 steps, count not available", "warn")]

    async def test_the_matching_revision_allows_a_deliberate_replacement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        ctx, _commit = context_and_commit(graph, [])
        built: list[dict[str, object]] = []

        async def _build(**kwargs: object) -> BuildOutcome:
            built.append(kwargs)
            return _outcome()

        _pin_build(monkeypatch, _build)

        await build_strategy(ctx, root=leaf("step_b"), base_revision=revision_of(graph))

        assert len(built) == 1


class TestRejectedBatchesAreRetryable:
    async def test_a_bad_operation_becomes_a_model_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An apply error becomes a retry, so the model can correct the
        operation."""
        graph = graph_with(leaf("step_a"))
        ctx, _commit = context_and_commit(graph, [])

        async def _boom(
            *, deps: StrategyMutationContext, ops: Sequence[GraphOperation]
        ) -> CommitResult:
            del deps, ops
            msg = "step 'ghost' not found"
            raise ApplyError(msg)

        pin_apply(monkeypatch, _boom)

        with pytest.raises(ModelRetry) as caught:
            await apply_operations(
                ctx,
                base_revision=revision_of(graph),
                operations=[UpdateStepMetaOp(step_id="ghost", display_name="x")],
            )

        assert "ghost" in str(caught.value)

    async def test_the_retry_says_the_revision_is_still_good(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rejected batch rolls back, so the same revision stays valid."""
        graph = graph_with(leaf("step_a"))
        ctx, _commit = context_and_commit(graph, [])

        async def _boom(
            *, deps: StrategyMutationContext, ops: Sequence[GraphOperation]
        ) -> CommitResult:
            del deps, ops
            msg = "nope"
            raise ApplyError(msg)

        pin_apply(monkeypatch, _boom)

        revision = revision_of(graph)
        with pytest.raises(ModelRetry) as caught:
            await apply_operations(
                ctx,
                base_revision=revision,
                operations=[UpdateStepMetaOp(step_id="a", display_name="x")],
            )

        assert revision in str(caught.value)


class TestToolSchema:
    def test_the_operation_union_survives_schema_generation(self) -> None:
        """The operation list is a discriminated union over models that nest a
        recursive node, and it must produce a JSON schema."""
        schema = Tool(apply_operations).function_schema.json_schema

        assert "base_revision" in schema["properties"]
        assert "operations" in schema["properties"]

    def test_the_model_reads_every_editable_operation_and_no_other(self) -> None:
        """The schema and the union are one list, read from the union itself."""
        schema = Tool(apply_operations).function_schema.json_schema
        defs = schema.get("$defs", {})
        offered = {
            name for name, spec in defs.items() if "kind" in spec.get("properties", {})
        }

        assert offered == {model.__name__ for model in editable_models()}

    def test_the_tool_is_registered_on_the_execution_toolset(self) -> None:
        toolset = unwrap_function_toolset(build_toolset())

        assert "apply_operations" in toolset.tools
