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
from veupathdb.domain.parameters.values import SinglePickValue

from pathfinder.platform.errors import sanitize_error_for_client
from pathfinder.services.experiment.service import run_experiment
from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import (
    BatchExperimentConfig,
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


async def stream_batch_experiment(
    batch_config: BatchExperimentConfig,
    *,
    user_id: str | None = None,
) -> AsyncIterator[BatchEvent]:
    """Run a batch experiment (one per organism) and yield typed events."""
    batch_id = f"batch_{int(asyncio.get_running_loop().time() * 1000)}"
    queue: asyncio.Queue[ExperimentProgressEvent] = asyncio.Queue()
    callback = _make_callback(queue)

    async def _run() -> tuple[list[Experiment], str | None]:
        results: list[Experiment] = []
        base = batch_config.base_config
        org_param = batch_config.organism_param_name
        store = get_experiment_store()
        try:
            for target in batch_config.target_organisms:
                params = dict(base.parameters)
                params[org_param] = SinglePickValue(value=target.organism)
                org_config = ExperimentConfig(
                    site_id=base.site_id,
                    record_type=base.record_type,
                    search_name=base.search_name,
                    parameters=params,
                    positive_controls=(
                        target.positive_controls
                        if target.positive_controls is not None
                        else list(base.positive_controls)
                    ),
                    negative_controls=(
                        target.negative_controls
                        if target.negative_controls is not None
                        else list(base.negative_controls)
                    ),
                    controls_search_name=base.controls_search_name,
                    controls_param_name=base.controls_param_name,
                    controls_value_format=base.controls_value_format,
                    enable_cross_validation=base.enable_cross_validation,
                    k_folds=base.k_folds,
                    enrichment_types=list(base.enrichment_types),
                    name=f"{base.name} ({target.organism})",
                    description=base.description,
                    parameter_display_values=(
                        dict(base.parameter_display_values)
                        if base.parameter_display_values
                        else None
                    ),
                )
                try:
                    exp = await run_experiment(
                        org_config,
                        user_id=user_id,
                        progress_callback=callback,
                    )
                except Exception as exc:
                    logger.exception(
                        "Batch organism experiment failed",
                        organism=target.organism,
                        error=str(exc),
                    )
                    continue
                exp.batch_id = batch_id
                store.save(exp)
                results.append(exp)
        except Exception as exc:
            logger.exception("Batch experiment failed", error=str(exc))
            return results, sanitize_error_for_client(exc)
        return results, None

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
