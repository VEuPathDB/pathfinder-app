from __future__ import annotations

import contextlib
from uuid import uuid4

import pytest

from pathfinder.services.experiment.control_sourcing import (
    control_ids_from_saved_gene_set,
    validate_control_ids,
)
from pathfinder.services.experiment.variant_comparison import (
    VariantSpec,
    run_variant_comparison,
)
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.tests.integration.strategies.conftest import (
    BuildAndRead,
    go_term_leaf,
    step_gene_ids,
    text_leaf,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


async def test_variant_comparison_real_counts_and_overlap(wdk_session: None) -> None:
    del wdk_session
    specs = [
        VariantSpec(
            label=expr,
            search_name="GenesByText",
            parameters=text_leaf(expr).parameters,
        )
        for expr in ("kinase", "phosphatase", "transferase")
    ]
    comparison = await run_variant_comparison("plasmodb", specs)

    by_label = {v.label: v for v in comparison.variants}
    assert {v.error for v in comparison.variants} == {None}
    assert by_label["kinase"].gene_count >= 100
    assert 20 <= by_label["phosphatase"].gene_count <= 200
    assert by_label["transferase"].gene_count <= 50
    # Kinases are mostly distinct from phosphatases/transferases.
    assert by_label["kinase"].unique_count >= 100

    pairs = {frozenset((o.a, o.b)): o for o in comparison.overlaps}
    kin_phos = pairs[frozenset(("kinase", "phosphatase"))]
    assert kin_phos.shared <= 15
    assert 0.0 <= kin_phos.jaccard < 0.2


async def test_gene_set_operations_match_ground_truth_on_real_sets(
    wdk_builder: BuildAndRead,
) -> None:
    _, kinase_ids = await step_gene_ids(await wdk_builder(text_leaf("kinase")))
    _, go_kinase_ids = await step_gene_ids(
        await wdk_builder(go_term_leaf("GO:0004672"))
    )
    assert len(kinase_ids) >= 100
    assert len(go_kinase_ids) >= 90

    user_id = uuid4()
    svc = GeneSetService(get_gene_set_store())
    created: list[str] = []
    try:
        set_a = await svc.create(
            user_id=user_id,
            name="kinase text",
            site_id="plasmodb",
            gene_ids=sorted(kinase_ids),
            source="paste",
        )
        set_b = await svc.create(
            user_id=user_id,
            name="GO kinases",
            site_id="plasmodb",
            gene_ids=sorted(go_kinase_ids),
            source="paste",
        )
        created += [set_a.id, set_b.id]

        async def op(operation: str) -> set[str]:
            result = await svc.perform_set_operation(
                user_id=user_id,
                set_a_id=set_a.id,
                set_b_id=set_b.id,
                operation=operation,
                name=operation,
            )
            created.append(result.id)
            return set(result.gene_ids)

        intersect = await op("intersect")
        union = await op("union")
        minus = await op("minus")

        assert intersect == kinase_ids & go_kinase_ids
        assert union == kinase_ids | go_kinase_ids
        assert minus == kinase_ids - go_kinase_ids

        # Real overlap is substantial but partial - proves a meaningful join,
        # not a trivial subset or disjoint pair.
        assert len(intersect) >= 80
        assert len(intersect) < len(kinase_ids)
        assert len(union) > max(len(kinase_ids), len(go_kinase_ids))
        assert len(minus) == len(kinase_ids) - len(intersect)
    finally:
        for gid in created:
            with contextlib.suppress(Exception):
                await svc.delete(user_id, gid)


async def test_validate_control_ids_splits_real_from_fake(
    wdk_builder: BuildAndRead,
) -> None:
    _, kinase_ids = await step_gene_ids(await wdk_builder(text_leaf("kinase")))
    real = sorted(kinase_ids)[:5]
    fakes = ["NOT_A_GENE_AAA", "BOGUS_999", "PF3D7_9999999"]

    resolved = await validate_control_ids("plasmodb", [*real, *fakes])

    assert set(resolved.valid_ids) == set(real)
    assert set(resolved.unresolved_ids) == set(fakes)
    assert len(resolved.valid_ids) == 5


async def test_validate_control_ids_dedups_and_preserves_order(
    wdk_builder: BuildAndRead,
) -> None:
    _, kinase_ids = await step_gene_ids(await wdk_builder(text_leaf("kinase")))
    real = sorted(kinase_ids)[:3]

    resolved = await validate_control_ids(
        "plasmodb", [real[0], real[1], real[0], real[2]]
    )

    assert resolved.valid_ids == real
    assert resolved.unresolved_ids == []


async def test_control_ids_from_saved_gene_set_round_trips(
    wdk_builder: BuildAndRead,
) -> None:
    _, kinase_ids = await step_gene_ids(await wdk_builder(text_leaf("kinase")))
    ids = sorted(kinase_ids)
    user_id = uuid4()
    svc = GeneSetService(get_gene_set_store())
    gs = await svc.create(
        user_id=user_id,
        name="kinase set",
        site_id="plasmodb",
        gene_ids=ids,
        source="paste",
    )
    try:
        pulled = await control_ids_from_saved_gene_set(user_id, gs.id)
        assert pulled == ids
    finally:
        await svc.delete(user_id, gs.id)
