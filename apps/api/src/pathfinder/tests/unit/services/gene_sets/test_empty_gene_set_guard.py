"""Saving a gene set that resolved to zero genes is never the intent.

Observed in UAT: the workbench listed two 0-gene sets, auto-imported from
strategies that returned nothing. A 0-gene set is inert everywhere it is used
(enrichment has no input, set operations return empty, export writes a header
row) and reads as a real result in the list, so it costs the researcher a
click to discover it is worthless.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import pytest
from veupathdb.errors import ValidationError
from veupathdb_mcp.wdk import GeneSetWdkContext

from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore


def _stub_resolve(
    monkeypatch: pytest.MonkeyPatch,
    resolved: list[str],
) -> None:
    async def _fake(
        site_id: str,
        gene_ids: Sequence[str],
        ctx: GeneSetWdkContext,
    ) -> tuple[list[str], GeneSetWdkContext, int]:
        del site_id
        # Mirrors the real short-circuit: explicit ids are never re-resolved.
        if gene_ids:
            return list(gene_ids), ctx, 1
        return resolved, ctx, 1

    monkeypatch.setattr(operations, "resolve_wdk_context", _fake)


async def test_creating_an_empty_gene_set_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_resolve(monkeypatch, [])
    store = GeneSetStore()

    with pytest.raises(ValidationError) as excinfo:
        await GeneSetService(store).create(
            user_id=uuid4(),
            name="Gametocyte markers",
            site_id="plasmodb",
            gene_ids=[],
            source="strategy",
            wdk=GeneSetWdkContext(wdk_strategy_id=330517023),
        )

    # The message must say what to do, not just that something failed.
    assert "0 genes" in str(excinfo.value.detail)
    assert store._cache == {}


async def test_a_resolved_gene_set_is_still_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_resolve(monkeypatch, ["PF3D7_0100100", "PF3D7_0100200"])
    store = GeneSetStore()

    gs = await GeneSetService(store).create(
        user_id=uuid4(),
        name="Gametocyte markers",
        site_id="plasmodb",
        gene_ids=[],
        source="strategy",
        wdk=GeneSetWdkContext(wdk_strategy_id=330517023),
    )

    assert gs.gene_ids == ["PF3D7_0100100", "PF3D7_0100200"]


async def test_a_set_operation_may_still_yield_an_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty intersection IS the answer the user asked for — never blocked."""
    _stub_resolve(monkeypatch, ["PF3D7_0100100"])
    store = GeneSetStore()
    svc = GeneSetService(store)
    user_id = uuid4()

    left = await svc.create(
        user_id=user_id,
        name="left",
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100"],
        source="paste",
    )
    right = await svc.create(
        user_id=user_id,
        name="right",
        site_id="plasmodb",
        gene_ids=["PF3D7_9999999"],
        source="paste",
    )

    derived = await svc.perform_set_operation(
        user_id=user_id,
        set_a_id=left.id,
        set_b_id=right.id,
        operation="intersect",
        name="no overlap",
    )

    assert derived.gene_ids == []
