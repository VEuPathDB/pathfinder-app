"""Seed runner. Creates real WDK strategies and curated control sets across sites."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import get_strategy_api

from pathfinder.persistence.repositories import (
    ConversationRepository,
)
from pathfinder.persistence.repositories.control_set import (
    ControlSetCreate,
    ControlSetRepository,
)
from pathfinder.platform.errors import sanitize_error_for_client
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.experiment.materialization import (
    _materialize_step_tree,
)
from pathfinder.services.experiment.seed.catalog import (
    get_all_seeds,
    get_seeds_for_site,
)
from pathfinder.services.experiment.seed.types import (
    SeedComplete,
    SeedDef,
    SeedEvent,
    SeedItemError,
    SeedProgress,
    SeedStrategyComplete,
)
from pathfinder.services.strategies.wdk_sync import sync_to_chat

logger = get_logger(__name__)

_MAX_CONCURRENT_SEEDS = 10


def _coerce_param_value(value: object) -> object:
    """Convert a seed parameter from WDK wire format into a typed ParamValue.

    A value that is already typed passes through unchanged.
    """
    if isinstance(value, dict) or not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except ValueError, TypeError:
        return {"type": "string", "value": value}
    if isinstance(parsed, list):
        return {"type": "multi-pick-vocabulary", "values": [str(x) for x in parsed]}
    if isinstance(parsed, dict) and ("min" in parsed or "max" in parsed):
        bounds: dict[str, object] = {"type": "number-range"}
        if parsed.get("min") not in (None, ""):
            bounds["min"] = float(parsed["min"])
        if parsed.get("max") not in (None, ""):
            bounds["max"] = float(parsed["max"])
        return bounds
    return {"type": "string", "value": value}


def _coerce_step_tree_params(node: object) -> object:
    """Recursively coerce every step's ``parameters`` to typed ParamValues."""
    if not isinstance(node, dict):
        return node
    result: dict[str, object] = dict(node)
    params = result.get("parameters")
    if isinstance(params, dict):
        result["parameters"] = {k: _coerce_param_value(v) for k, v in params.items()}
    for child_key in ("primaryInput", "secondaryInput"):
        if result.get(child_key) is not None:
            result[child_key] = _coerce_step_tree_params(result[child_key])
    return result


@dataclass
class _SeedRunContext:
    """Per-run resources shared by every seed."""

    total: int
    semaphore: asyncio.Semaphore
    queue: asyncio.Queue[SeedEvent | None]
    conv_repo: ConversationRepository
    control_set_repo: ControlSetRepository
    user_id: UUID


async def _process_single_seed(
    i: int,
    seed: SeedDef,
    ctx: _SeedRunContext,
) -> tuple[bool, bool]:
    """Create one seed strategy and its control set."""
    idx = i + 1
    async with ctx.semaphore:
        await ctx.queue.put(
            SeedProgress(
                phase="running",
                current=idx,
                total=ctx.total,
                name=seed.name,
                message=f"[{idx}/{ctx.total}] Creating strategy: {seed.name}",
            )
        )

        t0 = time.monotonic()
        try:
            api = get_strategy_api(seed.site_id)

            tree_node = StrategyStepNode.model_validate(
                _coerce_step_tree_params(seed.step_tree)
            )
            root_tree = await _materialize_step_tree(api, tree_node, seed.record_type)

            created = await api.create_strategy(
                step_tree=root_tree,
                name=seed.name,
                description=seed.description,
                is_saved=True,
            )
            wdk_strategy_id = created.id

            await sync_to_chat(
                wdk_id=wdk_strategy_id,
                site_id=seed.site_id,
                api=api,
                conv_repo=ctx.conv_repo,
                user_id=ctx.user_id,
                assistant_id=PATHFINDER_ASSISTANT_ID,
            )

            elapsed_strategy = time.monotonic() - t0
            await ctx.queue.put(
                SeedStrategyComplete(
                    current=idx,
                    total=ctx.total,
                    name=seed.name,
                    wdk_strategy_id=wdk_strategy_id,
                    elapsed=round(elapsed_strategy, 1),
                    message=f"[{idx}/{ctx.total}] Strategy created: {seed.name}",
                )
            )

            cs = seed.control_set
            await ctx.control_set_repo.create(
                ControlSetCreate(
                    name=cs.name,
                    site_id=seed.site_id,
                    record_type=seed.record_type,
                    positive_ids=cs.positive_ids,
                    negative_ids=cs.negative_ids,
                    source="curation",
                    tags=cs.tags or [],
                    provenance_notes=cs.provenance_notes,
                    is_public=True,
                    user_id=ctx.user_id,
                )
            )

        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.exception("Seed failed", name=seed.name, error=str(exc))
            await ctx.queue.put(
                SeedItemError(
                    current=idx,
                    total=ctx.total,
                    name=seed.name,
                    error=sanitize_error_for_client(exc),
                    elapsed=round(elapsed, 1),
                    message=f"[{idx}/{ctx.total}] Failed: {seed.name}",
                )
            )
            return (False, False)
        else:
            return (True, True)


async def run_seed(
    *,
    user_id: UUID,
    session: AsyncSession,
    site_id: str | None = None,
) -> AsyncIterator[SeedEvent]:
    """Create the seed strategies and control sets, yielding typed progress events.

    A ``site_id`` limits the run to the seeds of that site.
    """
    seeds = get_seeds_for_site(site_id) if site_id else get_all_seeds()
    total = len(seeds)
    yield SeedProgress(
        phase="starting",
        message=(
            f"Seeding {total} strategies and control sets "
            f"(up to {_MAX_CONCURRENT_SEEDS} concurrent)..."
        ),
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SEEDS)
    queue: asyncio.Queue[SeedEvent | None] = asyncio.Queue()
    run_ctx = _SeedRunContext(
        total=total,
        semaphore=semaphore,
        queue=queue,
        conv_repo=ConversationRepository(session),
        control_set_repo=ControlSetRepository(session),
        user_id=user_id,
    )

    async def _run_all() -> list[tuple[bool, bool]]:
        """Run every seed concurrently and put a sentinel on the queue at the end."""
        results: list[tuple[bool, bool]] = []
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(_process_single_seed(i, seed, run_ctx))
                    for i, seed in enumerate(seeds)
                ]
            results = [t.result() for t in tasks]
        except BaseException:
            logger.exception("Unexpected error in seed TaskGroup")
        finally:
            await queue.put(None)
        return results

    runner = asyncio.create_task(_run_all())

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

    results = await runner
    strategies_ok = sum(1 for s, _ in results if s)
    control_sets_ok = sum(1 for _, c in results if c)

    yield SeedComplete(
        total=total,
        strategies_created=strategies_ok,
        control_sets_created=control_sets_ok,
        failed=total - strategies_ok,
        message=(
            f"Seeding complete: {strategies_ok}/{total} strategies, "
            f"{control_sets_ok}/{total} control sets"
        ),
    )
