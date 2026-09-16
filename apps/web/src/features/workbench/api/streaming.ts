/**
 * Typed SSE streaming for experiment execution.
 *
 * Each endpoint takes the generated request type for its route, so a body that
 * omits a field the API requires does not compile.
 */

import type { Experiment } from "@pathfinder/shared";
import type { CreateBatchExperimentRequest } from "@pathfinder/shared/generated/types/CreateBatchExperimentRequest";
import type { CreateBenchmarkRequest } from "@pathfinder/shared/generated/types/CreateBenchmarkRequest";
import type { CreateExperimentRequest } from "@pathfinder/shared/generated/types/CreateExperimentRequest";
import { streamTypedEvents } from "@/lib/sse/typedEventStream";

// ── Event shapes emitted by the backend (camelCase wire format) ────────────

interface ExperimentProgressEvent {
  type: "experiment_progress";
  data: Record<string, unknown>;
}

interface ExperimentCompleteEvent {
  type: "experiment_complete";
  experiment: Experiment;
}

interface ExperimentErrorEvent {
  type: "experiment_error";
  error: string;
}

interface ExperimentEndEvent {
  type: "experiment_end";
}

export type ExperimentStreamEvent =
  | ExperimentProgressEvent
  | ExperimentCompleteEvent
  | ExperimentErrorEvent
  | ExperimentEndEvent;

interface BatchCompleteEvent {
  type: "batch_complete";
  batchId: string;
  experiments: Experiment[];
}

interface BatchErrorEvent {
  type: "batch_error";
  error: string;
}

export type BatchStreamEvent =
  ExperimentProgressEvent | BatchCompleteEvent | BatchErrorEvent;

interface BenchmarkCompleteEvent {
  type: "benchmark_complete";
  benchmarkId: string;
  experiments: Experiment[];
}

interface BenchmarkErrorEvent {
  type: "benchmark_error";
  error: string;
}

export type BenchmarkStreamEvent =
  ExperimentProgressEvent | BenchmarkCompleteEvent | BenchmarkErrorEvent;

// ── Public generators ──────────────────────────────────────────────────────

type RunOptions = {
  signal?: AbortSignal;
};

function buildRunOptions(body: unknown, signal: AbortSignal | undefined) {
  return {
    method: "POST",
    body,
    ...(signal !== undefined ? { signal } : {}),
  } as const;
}

export async function* createExperimentStream(
  request: CreateExperimentRequest,
  options: RunOptions = {},
): AsyncGenerator<ExperimentStreamEvent> {
  yield* streamTypedEvents<ExperimentStreamEvent>(
    "/api/v1/experiments",
    buildRunOptions(request, options.signal),
  );
}

export async function* createBatchExperimentStream(
  request: CreateBatchExperimentRequest,
  options: RunOptions = {},
): AsyncGenerator<BatchStreamEvent> {
  yield* streamTypedEvents<BatchStreamEvent>(
    "/api/v1/experiments/batch",
    buildRunOptions(request, options.signal),
  );
}

export async function* createBenchmarkStream(
  request: CreateBenchmarkRequest,
  options: RunOptions = {},
): AsyncGenerator<BenchmarkStreamEvent> {
  yield* streamTypedEvents<BenchmarkStreamEvent>(
    "/api/v1/experiments/benchmark",
    buildRunOptions(request, options.signal),
  );
}
