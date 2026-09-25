"""Three ways to keep the seed's genes that have a P. vivax P01 ortholog, read live.

The seed is P. falciparum 3D7 genes with a signal peptide and 2 to 99
transmembrane domains. Each form INTERSECTs a gene set with the seed, so each
answer is a subset of the seed.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    clone_with_fresh_ids,
)
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
    encode_params,
    get_strategy_api,
)
from veupathdb_mcp.wdk import fetch_gene_ids_from_step

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_RECORD_TYPE = "transcript"
_SOURCE = "Plasmodium falciparum 3D7"
_TARGET = "Plasmodium vivax P01"

Genes = Callable[[StrategyStepNode], Awaitable[frozenset[str]]]


def _seed() -> StrategyStepNode:
    organism = MultiPickValue(values=[_SOURCE])
    return _combine(
        CombineOp.INTERSECT,
        StrategyStepNode(
            search_name="GenesWithSignalPeptide",
            parameters={
                "organism": organism,
                "signalp_version": SinglePickValue(value="SignalP-6.0"),
            },
        ),
        StrategyStepNode(
            search_name="GenesByTransmembraneDomains",
            parameters={
                "organism": organism,
                "min_tm": StringValue(value="2"),
                "max_tm": StringValue(value="99"),
            },
        ),
    )


def _combine(
    operator: CombineOp, left: StrategyStepNode, right: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        operator=operator,
        primary_input=left,
        secondary_input=right,
    )


def _orthologs(
    organism: str, syntenic: str, source: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="GenesByOrthologs",
        parameters={
            "organism": MultiPickValue(values=[organism]),
            "isSyntenic": SinglePickValue(value=syntenic),
        },
        primary_input=source,
    )


def _round_trip(syntenic: str) -> StrategyStepNode:
    seed = _seed()
    there = _orthologs(_TARGET, syntenic, clone_with_fresh_ids(seed))
    return _combine(CombineOp.INTERSECT, seed, _orthologs(_SOURCE, syntenic, there))


def _profile() -> StrategyStepNode:
    profile = StrategyStepNode(
        search_name="GenesByOrthologPattern",
        parameters={
            "organism": MultiPickValue(values=[_SOURCE]),
            "included_species": StringValue(value="pvip"),
            "excluded_species": StringValue(value="n/a"),
            "profile_pattern": StringValue(value="%pvip:Y%"),
        },
    )
    return _combine(CombineOp.INTERSECT, _seed(), profile)


@pytest.fixture
async def root_genes(wdk_identity: str) -> AsyncGenerator[Genes]:
    """Push a tree as one strategy, answer its root's genes, and delete it all."""
    del wdk_identity
    api = get_strategy_api(_SITE)
    strategies: list[int] = []
    steps: list[int] = []

    async def push(node: StrategyStepNode) -> WDKStepTree:
        if node.primary_input is not None and node.secondary_input is not None:
            left = await push(node.primary_input)
            right = await push(node.secondary_input)
            operator = node.operator or CombineOp.INTERSECT
            made = await api.create_combined_step(
                CombinedStepSpec(
                    primary_step_id=left.step_id,
                    secondary_step_id=right.step_id,
                    boolean_operator=operator,
                ),
                record_type=_RECORD_TYPE,
            )
            steps.append(made.id)
            return WDKStepTree(
                step_id=made.id, primary_input=left, secondary_input=right
            )
        spec = NewStepSpec(
            search_name=node.search_name,
            search_config=WDKSearchConfig(parameters=encode_params(node.parameters)),
        )
        if node.primary_input is not None:
            inner = await push(node.primary_input)
            made = await api.create_transform_step(
                spec, inner.step_id, record_type=_RECORD_TYPE
            )
            steps.append(made.id)
            return WDKStepTree(step_id=made.id, primary_input=inner)
        made = await api.create_step(spec, record_type=_RECORD_TYPE)
        steps.append(made.id)
        return WDKStepTree(step_id=made.id)

    async def genes(root: StrategyStepNode) -> frozenset[str]:
        tree = await push(root)
        strategy = await api.create_strategy(
            tree, name="pathfinder-live-lane", is_internal=True
        )
        strategies.append(strategy.id)
        steps.clear()
        return frozenset(await fetch_gene_ids_from_step(api, step_id=tree.step_id))

    try:
        yield genes
    finally:
        # A strategy deletes the steps it holds; a step no strategy took is left.
        for strategy_id in reversed(strategies):
            with contextlib.suppress(Exception):
                await api.delete_strategy(strategy_id)
        for step_id in reversed(steps):
            with contextlib.suppress(Exception):
                await api.delete_step(step_id)


async def test_the_plain_round_trip_keeps_the_genes_the_profile_keeps(
    root_genes: Genes,
) -> None:
    seed = await root_genes(_seed())
    profile = await root_genes(_profile())
    plain = await root_genes(_round_trip("no"))

    assert 0 < len(plain) < len(seed), (len(seed), len(plain))
    assert plain == profile, sorted(plain ^ profile)


async def test_the_syntenic_round_trip_keeps_a_subset_of_the_plain_one(
    root_genes: Genes,
) -> None:
    plain = await root_genes(_round_trip("no"))
    syntenic = await root_genes(_round_trip("yes"))

    assert 0 < len(syntenic) < len(plain), (len(plain), len(syntenic))
    assert syntenic <= plain, sorted(syntenic - plain)
