"""A separation offer states what its own tree returns on the site.

Each run separates one plasmodb seed's controls, builds the offered spec as
steps on the account, and reads the built root back with a control test of its
own. The counts on both sides are the site's; the test types none of them in.
Everything the run and the check create is deleted.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
    encode_params,
    get_strategy_api,
)
from veupathdb_mcp.controls import leftover_strategy_ids, run_step_control_tests
from veupathdb_mcp.separation import SeparationRequest, SeparationUpdate

from pathfinder.domain.separation import (
    SEPARATION_BUDGET,
    SeparationMode,
    SeparationOffer,
)
from pathfinder.domain.strategy.spec_tree import build_step_tree
from pathfinder.platform.identity import SEPARATION_STRATEGY_NAME
from pathfinder.services.evidence.separation import separate_controls
from pathfinder.services.experiment.seed.catalog import get_seeds_for_site

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_RECORD_TYPE = "transcript"

# The built root's step id and the size the site counted for it.
Built = Callable[[StrategyStepNode], Awaitable[tuple[int, int | None]]]


@dataclass(frozen=True)
class _Read:
    """The controls a tree returns, its size, and the run's leftover strategies."""

    recovered: list[str]
    admitted: list[str]
    size: int | None
    leftovers: list[int]


async def _offer(seed_name: str, mode: SeparationMode) -> SeparationOffer:
    (seed,) = [s for s in get_seeds_for_site(_SITE) if s.name == seed_name]
    controls = seed.control_set
    assert controls is not None

    async def _row(update: SeparationUpdate) -> None:
        del update

    report = await separate_controls(
        _SITE,
        SeparationRequest(
            positives=controls.positive_ids,
            negatives=controls.negative_ids,
            mode=mode,
            budget=SEPARATION_BUDGET,
        ),
        task_id=uuid4(),
        progress=_row,
    )
    assert report.offer is not None, report.shortfall
    return report.offer


@pytest.fixture
async def built(wdk_identity: str) -> AsyncGenerator[Built]:
    """Push a tree as one strategy, answer its root, and delete it all."""
    del wdk_identity
    api = get_strategy_api(_SITE)
    strategies: list[int] = []

    async def push(node: StrategyStepNode) -> WDKStepTree:
        if node.primary_input is not None and node.secondary_input is not None:
            left = await push(node.primary_input)
            right = await push(node.secondary_input)
            made = await api.create_combined_step(
                CombinedStepSpec(
                    primary_step_id=left.step_id,
                    secondary_step_id=right.step_id,
                    boolean_operator=node.operator or CombineOp.INTERSECT,
                ),
                record_type=_RECORD_TYPE,
            )
            return WDKStepTree(
                step_id=made.id, primary_input=left, secondary_input=right
            )
        made = await api.create_step(
            NewStepSpec(
                search_name=node.search_name,
                search_config=WDKSearchConfig(
                    parameters=encode_params(node.parameters)
                ),
            ),
            record_type=_RECORD_TYPE,
        )
        return WDKStepTree(step_id=made.id)

    async def build(root: StrategyStepNode) -> tuple[int, int | None]:
        tree = await push(root)
        strategy = await api.create_strategy(
            tree, name="pathfinder-live-lane", is_internal=True
        )
        strategies.append(strategy.id)
        details = await api.get_strategy(strategy.id)
        return tree.step_id, details.steps[str(tree.step_id)].estimated_size

    try:
        yield build
    finally:
        for strategy_id in reversed(strategies):
            with contextlib.suppress(Exception):
                await api.delete_strategy(strategy_id)


async def _site_read(offer: SeparationOffer, built: Built) -> _Read:
    """The built offer's root as a control test of its own reads it."""
    root_step_id, size = await built(build_step_tree(offer.spec).root)
    positives = sorted([*offer.positive.returned, *offer.positive.not_returned])
    negatives = sorted([*offer.negative.returned, *offer.negative.not_returned])
    read = await run_step_control_tests(
        _SITE,
        root_step_id,
        positive_controls=positives,
        negative_controls=negatives,
    )
    assert read.positive is not None
    assert read.negative is not None
    leftovers = leftover_strategy_ids(
        await get_strategy_api(_SITE).list_strategies(), SEPARATION_STRATEGY_NAME
    )
    return _Read(
        recovered=read.positive.recovered_ids,
        admitted=read.negative.admitted_ids,
        size=size,
        leftovers=leftovers,
    )


def _stated(offer: SeparationOffer) -> _Read:
    """What the offer says its tree returns, and that the run left nothing."""
    return _Read(
        recovered=offer.positive.returned,
        admitted=offer.negative.returned,
        size=offer.result_size,
        leftovers=[],
    )


async def test_an_exact_offer_returns_the_controls_it_states(built: Built) -> None:
    offer = await _offer("PF3D7 Signal Peptide Genes", "exact")

    assert await _site_read(offer, built) == _stated(offer)


async def test_the_signal_peptide_controls_separate(built: Built) -> None:
    """The site's catalog holds the seed's own search, so a run finds it."""
    offer = await _offer("PF3D7 Signal Peptide Genes", "exact")
    read = await _site_read(offer, built)

    assert (offer.separates, len(read.recovered), read.admitted) == (True, 80, [])


async def test_a_similar_offer_returns_the_controls_it_states(built: Built) -> None:
    offer = await _offer("PF3D7 Erythrocyte Invasion Machinery", "similar")

    assert await _site_read(offer, built) == _stated(offer)
