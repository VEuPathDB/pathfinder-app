"""A strategy-linked gene set re-resolves against its strategy on every take.

A take reads the strategy's current root step, so a rebuilt strategy replaces
the set's genes and the whole WDK context the set was taken under.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import fields

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb_mcp.wdk import GeneSetWdkContext

from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.operations import EmptyResyncError, GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet

Resolved = tuple[list[str], GeneSetWdkContext, int]


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


async def _resync(store: GeneSetStore) -> GeneSet:
    out = await GeneSetService(store).resync_strategy(
        "g2", wdk_strategy_id=214626640, site_id="plasmodb"
    )
    assert out is not None
    return out


SIGNAL_PEPTIDE_GENES = ["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0300300"]
SIGNAL_PEPTIDE_PARAMS: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])
}


def _signal_peptide_set() -> GeneSet:
    """A set taken from a single-step strategy, as one re-sync finds it."""
    return GeneSet(
        id="g2",
        name="gametocyte secreted",
        site_id="plasmodb",
        gene_ids=list(SIGNAL_PEPTIDE_GENES),
        source="strategy",
        wdk_strategy_id=214626640,
        wdk_step_id=227292630,
        search_name="GenesWithSignalPeptide",
        record_type="transcript",
        parameters=dict(SIGNAL_PEPTIDE_PARAMS),
        step_count=1,
    )


def _resolver(
    ctx_out: GeneSetWdkContext,
    step_count: int,
    gene_ids: list[str] | None = None,
) -> Callable[[str, Sequence[str], GeneSetWdkContext], Awaitable[Resolved]]:
    """Stand in for the WDK read, answering one resolved context."""
    resolved = ["PF3D7_NEW"] if gene_ids is None else gene_ids

    async def _resolve(
        site_id: str, gene_ids_in: Sequence[str], ctx: GeneSetWdkContext
    ) -> Resolved:
        del site_id, gene_ids_in, ctx
        return (list(resolved), ctx_out, step_count)

    return _resolve


@pytest.mark.asyncio
async def test_a_resync_carries_the_search_name_record_type_and_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GeneSetStore()
    store.save(_signal_peptide_set())
    parameters: dict[str, ParamValue] = {
        "min_molecular_weight": StringValue(value="50000"),
        "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
    }
    monkeypatch.setattr(
        operations,
        "resolve_wdk_context",
        _resolver(
            GeneSetWdkContext(
                wdk_strategy_id=214626640,
                wdk_step_id=227292630,
                search_name="GenesByMolecularWeight",
                record_type="transcript",
                parameters=parameters,
            ),
            1,
        ),
    )

    out = await _resync(store)

    assert out.search_name == "GenesByMolecularWeight"
    assert out.record_type == "transcript"
    assert out.parameters == parameters


@pytest.mark.asyncio
async def test_a_resync_onto_another_root_step_replaces_the_previous_search_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GeneSetStore()
    store.save(_signal_peptide_set())
    monkeypatch.setattr(
        operations,
        "resolve_wdk_context",
        _resolver(
            GeneSetWdkContext(
                wdk_strategy_id=214626640,
                wdk_step_id=227292999,
                search_name="GenesByGeneType",
                record_type="transcript",
                parameters={"gene_type": StringValue(value="protein coding")},
            ),
            1,
        ),
    )

    out = await _resync(store)

    assert out.wdk_step_id == 227292999
    assert out.search_name == "GenesByGeneType"
    assert out.parameters == {"gene_type": StringValue(value="protein coding")}


@pytest.mark.asyncio
async def test_a_resync_onto_a_multi_step_strategy_records_no_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A strategy with more than one step has no single search to record."""
    store = GeneSetStore()
    store.save(_signal_peptide_set())
    monkeypatch.setattr(
        operations,
        "resolve_wdk_context",
        _resolver(
            GeneSetWdkContext(
                wdk_strategy_id=214626640,
                wdk_step_id=227293100,
                search_name=None,
                record_type="transcript",
                parameters=None,
            ),
            3,
        ),
    )

    out = await _resync(store)

    assert out.search_name is None
    assert out.parameters is None
    assert out.step_count == 3


def test_every_field_of_a_resolved_context_reaches_the_gene_set() -> None:
    """A field added to the context cannot be left behind by a take."""
    gs = _signal_peptide_set()
    ctx = GeneSetWdkContext(
        wdk_strategy_id=1,
        wdk_step_id=2,
        search_name="GenesByTaxon",
        record_type="gene",
        parameters={"organism": StringValue(value="Plasmodium falciparum 3D7")},
    )

    gs.take_wdk_context(ctx, step_count=1)

    carried = {field.name: getattr(ctx, field.name) for field in fields(ctx)}
    assert carried == {
        "wdk_strategy_id": 1,
        "wdk_step_id": 2,
        "search_name": "GenesByTaxon",
        "record_type": "gene",
        "parameters": {"organism": StringValue(value="Plasmodium falciparum 3D7")},
    }
    assert {name: getattr(gs, name) for name in carried} == carried


def _other_root_context() -> GeneSetWdkContext:
    """What a re-sync resolves when the strategy now roots on another step."""
    return GeneSetWdkContext(
        wdk_strategy_id=214626640,
        wdk_step_id=227292999,
        search_name="GenesByGeneType",
        record_type="transcript",
        parameters={"gene_type": StringValue(value="protein coding")},
    )


@pytest.mark.asyncio
async def test_a_resync_that_reads_no_genes_leaves_the_set_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resolution with no genes has learnt nothing, so it writes nothing."""
    store = GeneSetStore()
    store.save(_signal_peptide_set())
    monkeypatch.setattr(
        operations,
        "resolve_wdk_context",
        _resolver(_other_root_context(), 1, gene_ids=[]),
    )

    with pytest.raises(EmptyResyncError) as caught:
        await GeneSetService(store).resync_strategy(
            "g2", wdk_strategy_id=214626640, site_id="plasmodb"
        )

    assert "gametocyte secreted" in str(caught.value.detail)
    kept = store.get("g2")
    assert kept is not None
    assert kept.gene_ids == SIGNAL_PEPTIDE_GENES
    assert kept.search_name == "GenesWithSignalPeptide"
    assert kept.wdk_step_id == 227292630
    assert kept.parameters == SIGNAL_PEPTIDE_PARAMS


@pytest.mark.asyncio
async def test_a_resync_that_reads_a_smaller_real_list_replaces_the_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A strategy that holds fewer genes than before is still a resolution."""
    store = GeneSetStore()
    store.save(_signal_peptide_set())
    monkeypatch.setattr(
        operations,
        "resolve_wdk_context",
        _resolver(
            _other_root_context(), 1, gene_ids=["PF3D7_0100100", "PF3D7_0200200"]
        ),
    )

    out = await _resync(store)

    assert out.gene_ids == ["PF3D7_0100100", "PF3D7_0200200"]
    assert out.search_name == "GenesByGeneType"
    assert out.parameters == {"gene_type": StringValue(value="protein coding")}
