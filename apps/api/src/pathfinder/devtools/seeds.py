"""Measure each seed's step tree against its control set on a live site.

Usage::

    python -m pathfinder.devtools.seeds measure --site plasmodb
    python -m pathfinder.devtools.seeds marks

``measure`` signs in as the dev account of the settings. ``marks`` records the
organism parameter of each search the seeds run.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path

from veupathdb.domain.strategy import (
    leaves,
)
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    get_strategy_api,
    password_login,
)
from veupathdb_mcp.catalog import organism_parameter, resolve_search_record_type
from veupathdb_mcp.controls import leftover_strategy_ids, run_step_control_tests

from pathfinder.ai.models.mock.site_values import MARKS_FILE
from pathfinder.jobs.auth_context import attach_wdk_auth
from pathfinder.platform.config import get_settings
from pathfinder.services.experiment.controls_search import controls_search
from pathfinder.services.experiment.materialization import materialize_step_tree
from pathfinder.services.experiment.seed.catalog import (
    SEEDS_DIR,
    get_seeds_for_site,
    seed_databases,
)
from pathfinder.services.experiment.seed.types import SeedDef, SeedMeasurement
from pathfinder.services.wdk_build import site_build

STRATEGY_NAME = "pathfinder seed measure"


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
        tree = await materialize_step_tree(seed.site_id, root, made)
        strategy_id = (
            await api.create_strategy(tree, name=STRATEGY_NAME, is_internal=True)
        ).id
        read = await run_step_control_tests(
            seed.site_id,
            tree.step_id,
            positive_controls=controls.positive_ids,
            negative_controls=controls.negative_ids,
            controls=controls_search(seed.record_type),
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
    settings = get_settings()
    email = settings.wdk_dev_email
    password = settings.wdk_dev_password.get_secret_value()
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


async def seed_organism_marks() -> dict[str, dict[str, str | None]]:
    """Each seed site, and the organism parameter each search its seeds run marks."""
    recorded: dict[str, dict[str, str | None]] = {}
    for site_id in seed_databases():
        searches = {
            (leaf.search_name, seed.record_type)
            for seed in get_seeds_for_site(site_id)
            for leaf in leaves(seed.step_node())
        }
        recorded[site_id] = {
            name: await organism_parameter(
                site_id,
                await resolve_search_record_type(site_id, name, record_type),
                name,
            )
            for name, record_type in sorted(searches)
        }
    return recorded


def marks_json(recorded: dict[str, dict[str, str | None]]) -> str:
    """The marks file's text, in the layout it keeps."""
    return json.dumps(recorded, indent=2, sort_keys=True) + "\n"


async def record_marks() -> None:
    MARKS_FILE.write_text(marks_json(await seed_organism_marks()))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pathfinder.devtools.seeds")
    parser.add_argument("command", choices=["measure", "marks"])
    parser.add_argument("--site")
    args = parser.parse_args()
    if args.command == "marks":
        asyncio.run(record_marks())
        return
    if args.site is None:
        parser.error("measure needs --site")
    asyncio.run(measure(args.site))


if __name__ == "__main__":
    main()
