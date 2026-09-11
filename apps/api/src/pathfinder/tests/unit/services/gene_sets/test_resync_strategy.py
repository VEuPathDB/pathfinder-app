"""A strategy-linked gene set must re-resolve when its strategy is rebuilt.

The auto-import resolves genes once at first build and latches; a re-run that
changed the result (e.g. a relaxed threshold) would otherwise leave the set
frozen at the stale snapshot — reporting 0 while the strategy holds N genes.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb_mcp.wdk import GeneSetWdkContext

from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet


@pytest.mark.asyncio
async def test_resync_strategy_replaces_stale_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GeneSetStore()
    store.save(
        GeneSet(
            id="g1",
            name="Immunogenic candidates",
            site_id="plasmodb",
            gene_ids=[],
            source="strategy",
            wdk_strategy_id=330427013,
            wdk_step_id=439858733,
            record_type="transcript",
            step_count=0,
        )
    )
    svc = GeneSetService(store)

    async def _fake_resolve(
        site_id: str, gene_ids: Sequence[str], ctx: GeneSetWdkContext
    ) -> tuple[list[str], GeneSetWdkContext, int]:
        del site_id, gene_ids
        # The fix: NO stale step id is passed, so the CURRENT root is resolved.
        assert ctx.wdk_step_id is None
        return (
            ["PF3D7_A", "PF3D7_B", "PF3D7_A"],
            GeneSetWdkContext(
                wdk_strategy_id=ctx.wdk_strategy_id,
                wdk_step_id=439858933,
                record_type="transcript",
            ),
            4,
        )

    monkeypatch.setattr(operations, "resolve_wdk_context", _fake_resolve)

    out = await svc.resync_strategy("g1", wdk_strategy_id=330427013, site_id="plasmodb")

    assert out is not None
    assert out.gene_ids == ["PF3D7_A", "PF3D7_B"]  # fresh + deduped
    assert out.wdk_step_id == 439858933  # re-resolved to the rebuilt root
    assert out.step_count == 4
