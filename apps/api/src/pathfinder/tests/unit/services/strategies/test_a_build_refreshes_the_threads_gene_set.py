"""A build that reaches the site defers the refresh of the thread's gene set."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import spec_build
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api, leaf


async def test_a_built_strategy_defers_the_refresh_after_it_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    writes: list[str] = []

    async def _persist(**_kwargs: Any) -> None:
        writes.append("persist")

    async def _defer(deps: StrategyMutationContext) -> None:
        writes.append(f"defer {deps.site_id}")

    monkeypatch.setattr(spec_build, "persist_strategy_ast_to_conversation", _persist)
    monkeypatch.setattr(spec_build, "defer_the_gene_set_refresh", _defer)
    graph = StrategyGraph("g1", "Taxon", "plasmodb")
    graph.record_type = "transcript"
    session = StrategySession(site_id="plasmodb")
    session.graph = graph

    outcome = await build_strategy_from_spec(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        root=leaf("step_a", {"organism": StringValue(value="P. falciparum 3D7")}),
    )

    assert outcome.wdk_strategy_id == 42
    assert writes == ["persist", "persist", "defer plasmodb"]
