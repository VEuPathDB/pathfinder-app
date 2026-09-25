"""Measure each seed's own step tree against its control set on the live site.

Each seed's tree is built as one internal strategy on the account, its root is
read with a control test of the seed's positives and negatives, and the counts
are written into the seed as ``measured``, dated with the site's build. The
strategy is deleted, and the run confirms the account holds none it left.

Usage::

    python -m pathfinder.devtools.seeds measure --site plasmodb

The run signs in as the dev account the environment names.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

from pydantic import ConfigDict
from veupathdb.domain.strategy import DEFAULT_COMBINE_OPERATOR, StrategyStepNode
from veupathdb.errors import VEuPathDBError, validate_response
from veupathdb.model import CamelModel
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    StrategyAPI,
    WDKSearchConfig,
    WDKStepTree,
    encode_params,
    get_strategy_api,
    get_wdk_client,
    password_login,
)
from veupathdb_mcp.controls import leftover_strategy_ids, run_step_control_tests

from pathfinder.jobs.auth_context import attach_wdk_auth
from pathfinder.services.experiment.seed.catalog import SEEDS_DIR, get_seeds_for_site
from pathfinder.services.experiment.seed.types import SeedDef, SeedMeasurement

STRATEGY_NAME = "pathfinder seed measure"


class _ServiceRoot(CamelModel):
    model_config = ConfigDict(extra="ignore")

    build_number: str


async def site_build(site_id: str) -> str:
    """The build number the site's service root reports."""
    raw = await get_wdk_client(site_id).get("/")
    return validate_response(_ServiceRoot, raw, "WDK service root").build_number


async def _push(
    api: StrategyAPI, node: StrategyStepNode, record_type: str, made: list[int]
) -> WDKStepTree:
    """Create the steps of a seed tree, inputs first, and note each step id."""
    if node.primary_input is None or node.secondary_input is None:
        step = await api.create_step(
            NewStepSpec(
                search_name=node.search_name,
                search_config=WDKSearchConfig(
                    parameters=encode_params(node.parameters)
                ),
                custom_name=node.display_name or node.search_name,
            ),
            record_type=record_type,
        )
        made.append(step.id)
        return WDKStepTree(step_id=step.id)
    left = await _push(api, node.primary_input, record_type, made)
    right = await _push(api, node.secondary_input, record_type, made)
    combined = await api.create_combined_step(
        CombinedStepSpec(
            primary_step_id=left.step_id,
            secondary_step_id=right.step_id,
            boolean_operator=node.operator or DEFAULT_COMBINE_OPERATOR,
            custom_name=node.display_name or "combine",
        ),
        record_type=record_type,
    )
    made.append(combined.id)
    return WDKStepTree(step_id=combined.id, primary_input=left, secondary_input=right)


async def measure_seed(
    seed: SeedDef, build: str, date: datetime.date
) -> SeedMeasurement:
    """The seed's controls as its own tree returns them, or the site's refusal."""
    api = get_strategy_api(seed.site_id)
    controls = seed.control_set
    stamp = {
        "site_build": build,
        "date": date,
        "positives_total": len(controls.positive_ids),
        "negatives_total": len(controls.negative_ids),
    }
    made: list[int] = []
    strategy_id: int | None = None
    try:
        root = seed.step_node()
        tree = await _push(api, root, seed.record_type, made)
        strategy_id = (
            await api.create_strategy(tree, name=STRATEGY_NAME, is_internal=True)
        ).id
        read = await run_step_control_tests(
            seed.site_id,
            tree.step_id,
            positive_controls=controls.positive_ids,
            negative_controls=controls.negative_ids,
        )
    except VEuPathDBError as exc:
        return SeedMeasurement.model_validate({**stamp, "refusal": str(exc)})
    finally:
        if strategy_id is not None:
            await api.delete_strategy(strategy_id)
        else:
            await api.delete_orphaned_steps(made)
    return SeedMeasurement.model_validate(
        {
            **stamp,
            "root_count": read.target.estimated_size,
            "positives_recovered": len(read.positive.recovered_ids)
            if read.positive
            else 0,
            "negatives_admitted": len(read.negative.admitted_ids)
            if read.negative
            else 0,
        }
    )


def seeds_json(seeds: list[SeedDef]) -> str:
    """The seed file's text, in the layout every seed file keeps."""
    dumped = [seed.model_dump(mode="json", exclude_none=True) for seed in seeds]
    return json.dumps(dumped, indent=2, sort_keys=True) + "\n"


def _seed_file(site_id: str) -> Path:
    return Path(str(SEEDS_DIR / f"{site_id}.json"))


def _line(seed: SeedDef) -> str:
    measured = seed.measured
    if measured is None:
        return f"{seed.name}: not measured\n"
    if measured.refusal is not None:
        return f"{seed.name}: build {measured.site_build}: {measured.refusal}\n"
    return (
        f"{seed.name}: build {measured.site_build}, root {measured.root_count}, "
        f"positives {measured.positives_recovered}/{measured.positives_total}, "
        f"negatives {measured.negatives_admitted}/{measured.negatives_total}\n"
    )


async def measure_site(site_id: str) -> list[SeedDef]:
    """Measure every seed of a site, and confirm the run left no strategy."""
    build = await site_build(site_id)
    today = datetime.datetime.now(datetime.UTC).date()
    measured = [
        seed.model_copy(update={"measured": await measure_seed(seed, build, today)})
        for seed in get_seeds_for_site(site_id)
    ]
    left = leftover_strategy_ids(
        await get_strategy_api(site_id).list_strategies(), STRATEGY_NAME
    )
    if left:
        msg = f"the run left strategies {left} on {site_id}"
        raise RuntimeError(msg)
    return measured


async def dev_login(site_id: str) -> str:
    """The dev account's WDK token on ``site_id``."""
    email = os.environ.get("WDK_DEV_EMAIL", "")
    password = os.environ.get("WDK_DEV_PASSWORD", "")
    token = await password_login(site_id, email, password) if email else None
    if not token:
        msg = f"the dev login did not sign in on {site_id}"
        raise RuntimeError(msg)
    return token


async def measure(site_id: str) -> None:
    async with attach_wdk_auth(await dev_login(site_id)):
        seeds = await measure_site(site_id)
    _seed_file(site_id).write_text(seeds_json(seeds))
    for seed in seeds:
        sys.stdout.write(_line(seed))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pathfinder.devtools.seeds")
    parser.add_argument("command", choices=["measure"])
    parser.add_argument("--site", required=True)
    args = parser.parse_args()
    asyncio.run(measure(args.site))


if __name__ == "__main__":
    main()
