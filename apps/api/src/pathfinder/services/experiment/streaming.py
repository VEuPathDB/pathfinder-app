"""Streaming wrappers for experiment execution.

Async generators wrap experiment runs and yield typed events for direct
server-sent-event responses.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, Literal

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import Field
from veupathdb.domain.parameters import SinglePickValue

from pathfinder.platform.errors import sanitize_error_for_client
from pathfinder.services.experiment.service import run_experiment
from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import (
    BatchExperimentConfig,
    BatchOrganismTarget,
    Experiment,
    ExperimentConfig,
    experiment_to_json,
)

logger = get_logger(__name__)


# --- Typed events ---------------------------------------------------------


class ExperimentProgressEvent(CamelModel):
    """Free-form progress event emitted during experiment execution."""

    type: Literal["experiment_progress"] = "experiment_progress"
    data: JSONObject = Field(default_factory=dict)


class ExperimentCompleteEvent(CamelModel):
    type: Literal["experiment_complete"] = "experiment_complete"
    experiment: JSONObject


class ExperimentErrorEvent(CamelModel):
    type: Literal["experiment_error"] = "experiment_error"
    error: str


class ExperimentEndEvent(CamelModel):
    type: Literal["experiment_end"] = "experiment_end"


class BatchCompleteEvent(CamelModel):
    type: Literal["batch_complete"] = "batch_complete"
    batch_id: str
    experiments: list[JSONObject]


class BatchErrorEvent(CamelModel):
    type: Literal["batch_error"] = "batch_error"
    error: str


class BenchmarkCompleteEvent(CamelModel):
    type: Literal["benchmark_complete"] = "benchmark_complete"
    benchmark_id: str
    experiments: list[JSONObject]


class BenchmarkErrorEvent(CamelModel):
    type: Literal["benchmark_error"] = "benchmark_error"
    error: str


ExperimentEvent = (
    ExperimentProgressEvent
    | ExperimentCompleteEvent
    | ExperimentErrorEvent
    | ExperimentEndEvent
)
BatchEvent = ExperimentProgressEvent | BatchCompleteEvent | BatchErrorEvent
BenchmarkEvent = ExperimentProgressEvent | BenchmarkCompleteEvent | BenchmarkErrorEvent


# --- Helpers --------------------------------------------------------------


_ProgressCallback = Callable[[JSONObject], Coroutine[Any, Any, None]]


def _progress_event_from_raw(evt: JSONObject) -> ExperimentProgressEvent:
    """Wrap a raw progress dict as a typed event."""
    raw_data = evt.get("data")
    data = raw_data if isinstance(raw_data, dict) else evt
    return ExperimentProgressEvent(data=data)


def _make_callback(
    queue: asyncio.Queue[ExperimentProgressEvent],
) -> _ProgressCallback:
    """Build a progress callback that enqueues typed events."""

    async def _cb(evt: JSONObject) -> None:
        await queue.put(_progress_event_from_raw(evt))

    return _cb


async def _cancel_task_silently(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# --- Public async generators ----------------------------------------------


async def stream_experiment(
    config: ExperimentConfig,
    *,
    user_id: str | None = None,
) -> AsyncIterator[ExperimentEvent]:
    """Run a single experiment and yield typed events as they occur."""
    queue: asyncio.Queue[ExperimentProgressEvent] = asyncio.Queue()
    callback = _make_callback(queue)

    async def _run() -> tuple[Experiment | None, str | None]:
        try:
            result = await run_experiment(
                config,
                user_id=user_id,
                progress_callback=callback,
            )
        except Exception as exc:
            logger.exception("Experiment failed", error=str(exc))
            return None, sanitize_error_for_client(exc)
        return result, None

    task = asyncio.create_task(_run())
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {get_task, task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if get_task in done:
                yield get_task.result()
            else:
                await _cancel_task_silently(get_task)
            if task.done():
                break
        while not queue.empty():
            yield queue.get_nowait()

        result, error = await task
        if error is not None:
            yield ExperimentErrorEvent(error=error)
        elif result is not None:
            yield ExperimentCompleteEvent(experiment=experiment_to_json(result))
        yield ExperimentEndEvent()
    finally:
        await _cancel_task_silently(task)


def organism_varies_nothing(base: ExperimentConfig) -> str | None:
    """Name the reason the organism parameter changes nothing for this base.

    Such a batch would run the same evaluation once per organism and label
    each result with an organism it did not use.
    """
    if base.target_gene_ids:
        return "the base evaluates a fixed gene list, which runs no search"
    if base.is_tree_mode:
        return "the base runs a step tree, which holds its own organism parameters"
    return None


def organism_config(
    base: ExperimentConfig,
    organism_param_name: str,
    target: BatchOrganismTarget,
) -> ExperimentConfig:
    """Derive one organism's config from the batch base.

    The copy carries every field the base names, so a field this function does
    not override reaches the organism's experiment unchanged.
    """
    parameters = dict(base.parameters)
    parameters[organism_param_name] = SinglePickValue(value=target.organism)
    return base.model_copy(
        deep=True,
        update={
            "parameters": parameters,
            "positive_controls": (
                target.positive_controls
                if target.positive_controls is not None
                else list(base.positive_controls)
            ),
            "negative_controls": (
                target.negative_controls
                if target.negative_controls is not None
                else list(base.negative_controls)
            ),
            "name": f"{base.name} ({target.organism})",
        },
    )


async def _run_one_organism(
    base: ExperimentConfig,
    org_param: str,
    target: BatchOrganismTarget,
    callback: _ProgressCallback,
    user_id: str | None,
) -> Experiment | None:
    """Run one organism's experiment. A failed organism does not end the batch."""
    try:
        return await run_experiment(
            organism_config(base, org_param, target),
            user_id=user_id,
            progress_callback=callback,
        )
    except Exception as exc:
        logger.exception(
            "Batch organism experiment failed",
            organism=target.organism,
            error=str(exc),
        )
        return None


async def _run_batch(
    batch_config: BatchExperimentConfig,
    batch_id: str,
    callback: _ProgressCallback,
    *,
    user_id: str | None,
) -> tuple[list[Experiment], str | None]:
    """Run one experiment per organism and return them with any batch failure."""
    results: list[Experiment] = []
    base = batch_config.base_config
    blocked = organism_varies_nothing(base)
    if blocked is not None:
        return results, f"This batch cannot vary by organism: {blocked}."
    store = get_experiment_store()
    try:
        for target in batch_config.target_organisms:
            exp = await _run_one_organism(
                base,
                batch_config.organism_param_name,
                target,
                callback,
                user_id,
            )
            if exp is None:
                continue
            exp.batch_id = batch_id
            store.save(exp)
            results.append(exp)
    except Exception as exc:
        logger.exception("Batch experiment failed", error=str(exc))
        return results, sanitize_error_for_client(exc)
    return results, None


async def stream_batch_experiment(
    batch_config: BatchExperimentConfig,
    *,
    user_id: str | None = None,
) -> AsyncIterator[BatchEvent]:
    """Run a batch experiment (one per organism) and yield typed events."""
    batch_id = f"batch_{int(asyncio.get_running_loop().time() * 1000)}"
    queue: asyncio.Queue[ExperimentProgressEvent] = asyncio.Queue()
    callback = _make_callback(queue)

    task = asyncio.create_task(
        _run_batch(batch_config, batch_id, callback, user_id=user_id),
    )
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {get_task, task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if get_task in done:
                yield get_task.result()
            else:
                await _cancel_task_silently(get_task)
            if task.done():
                break
        while not queue.empty():
            yield queue.get_nowait()
        results, error = await task
        if error is not None:
            yield BatchErrorEvent(error=error)
        else:
            yield BatchCompleteEvent(
                batch_id=batch_id,
                experiments=[experiment_to_json(e) for e in results],
            )
    finally:
        await _cancel_task_silently(task)


async def stream_benchmark(
    base_config: ExperimentConfig,
    control_sets: list[tuple[str, list[str], list[str], str | None, bool]],
    *,
    user_id: str | None = None,
) -> AsyncIterator[BenchmarkEvent]:
    """Run a benchmark suite (one experiment per control set) and yield typed events."""
    benchmark_id = f"bench_{int(asyncio.get_running_loop().time() * 1000)}"
    queue: asyncio.Queue[ExperimentProgressEvent] = asyncio.Queue()
    callback = _make_callback(queue)

    async def _run_one(
        label: str,
        positives: list[str],
        negatives: list[str],
        control_set_id: str | None,
        *,
        is_primary: bool,
    ) -> Experiment | None:
        cfg = copy.deepcopy(base_config)
        cfg.positive_controls = positives
        cfg.negative_controls = negatives
        cfg.name = f"{base_config.name} [{label}]"
        cfg.control_set_id = control_set_id
        try:
            exp = await run_experiment(cfg, user_id=user_id, progress_callback=callback)
        except Exception as exc:
            logger.exception(
                "Benchmark experiment failed",
                label=label,
                error=str(exc),
            )
            return None
        exp.benchmark_id = benchmark_id
        exp.control_set_label = label
        exp.is_primary_benchmark = is_primary
        get_experiment_store().save(exp)
        return exp

    async def _run() -> tuple[list[Experiment], str | None]:
        try:
            tasks = [
                _run_one(label, pos, neg, csid, is_primary=primary)
                for label, pos, neg, csid, primary in control_sets
            ]
            results = await asyncio.gather(*tasks)
        except Exception as exc:
            logger.exception("Benchmark suite failed", error=str(exc))
            return [], sanitize_error_for_client(exc)
        return [r for r in results if r is not None], None

    task = asyncio.create_task(_run())
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {get_task, task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if get_task in done:
                yield get_task.result()
            else:
                await _cancel_task_silently(get_task)
            if task.done():
                break
        while not queue.empty():
            yield queue.get_nowait()
        completed, error = await task
        if error is not None:
            yield BenchmarkErrorEvent(error=error)
        else:
            yield BenchmarkCompleteEvent(
                benchmark_id=benchmark_id,
                experiments=[experiment_to_json(e) for e in completed],
            )
    finally:
        await _cancel_task_silently(task)
