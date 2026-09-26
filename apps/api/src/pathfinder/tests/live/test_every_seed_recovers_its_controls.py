"""Every seed's own tree returns the controls its record states, on its own site.

Each seed's tree is built on the account and its root read with a control test,
through the same code the seed measurer writes the record with. Everything the
check creates is deleted.
"""

from __future__ import annotations

import datetime

import pytest
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.controls import leftover_strategy_ids

from pathfinder.devtools.seeds import STRATEGY_NAME, measure_seed
from pathfinder.services.experiment.seed.catalog import (
    SEED_DATABASES,
    get_seeds_for_site,
)
from pathfinder.services.experiment.seed.types import SeedDef, SeedMeasurement
from pathfinder.services.wdk_build import site_build

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio, pytest.mark.slow]


def _controls(measured: SeedMeasurement) -> tuple[int | None, int, int | None, int]:
    return (
        measured.positives_recovered,
        measured.positives_total,
        measured.negatives_admitted,
        measured.negatives_total,
    )


async def _read(
    seed: SeedDef, build: str
) -> tuple[str | None, float | None, tuple[int | None, int, int | None, int]]:
    today = datetime.datetime.now(datetime.UTC).date()
    live = await measure_seed(seed, build, today)
    return live.refusal, live.recall, _controls(live)


@pytest.mark.parametrize("site_id", SEED_DATABASES)
async def test_every_seed_tree_recovers_every_positive_it_records(
    site_id: str, wdk_identity: str
) -> None:
    del wdk_identity
    seeds = get_seeds_for_site(site_id)
    build = await site_build(site_id)

    read = {seed.name: await _read(seed, build) for seed in seeds}
    left = leftover_strategy_ids(
        await get_strategy_api(site_id).list_strategies(), STRATEGY_NAME
    )

    assert (read, left) == (
        {
            seed.name: (None, 1.0, _controls(seed.measured))
            for seed in seeds
            if seed.measured is not None
        },
        [],
    )
