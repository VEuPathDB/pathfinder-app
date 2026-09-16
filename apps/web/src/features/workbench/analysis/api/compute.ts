/**
 * Shared analysis API types and functions -- used by both workbench and analysis features.
 */

import type { CustomEnrichRequest } from "@pathfinder/shared/generated/types/CustomEnrichRequest";
import type { CustomEnrichmentResult } from "@pathfinder/shared/generated/types/CustomEnrichmentResult";
import type { ThresholdSweepRequest } from "@pathfinder/shared/generated/types/ThresholdSweepRequest";
import { customEnrichmentResultSchema } from "@pathfinder/shared/generated/zod/customEnrichmentResultSchema";

import { buildUrl, requestJson } from "@/lib/api/http";
import { streamTypedEvents } from "@/lib/sse/typedEventStream";

// ---------------------------------------------------------------------------
// Custom Enrichment
// ---------------------------------------------------------------------------

export async function runCustomEnrichment(
  experimentId: string,
  geneSetName: string,
  geneIds: string[],
): Promise<CustomEnrichmentResult> {
  const body: CustomEnrichRequest = { geneSetName, geneIds };
  return requestJson(
    customEnrichmentResultSchema,
    `/api/v1/experiments/${experimentId}/custom-enrich`,
    { method: "POST", body },
  );
}

// ---------------------------------------------------------------------------
// Threshold Sweep
// ---------------------------------------------------------------------------

export interface ThresholdSweepPoint {
  value: number | string;
  metrics: {
    sensitivity: number;
    specificity: number;
    precision: number;
    f1Score: number;
    mcc: number;
    balancedAccuracy: number;
    totalResults: number;
    falsePositiveRate: number;
  } | null;
  error?: string;
}

export interface ThresholdSweepResult {
  parameter: string;
  sweepType?: "numeric" | "categorical";
  points: ThresholdSweepPoint[];
}

// The route accepts min, max, steps and values as optional and pairs them at
// run time. These two say which pairing each sweep sends.
interface NumericSweepRequest extends ThresholdSweepRequest {
  sweepType: "numeric";
  min: number;
  max: number;
  steps: number;
}

interface CategoricalSweepRequest extends ThresholdSweepRequest {
  sweepType: "categorical";
  values: string[];
}

export type SweepRequest = NumericSweepRequest | CategoricalSweepRequest;

interface SweepPointEvent {
  type: "sweep_point";
  point: ThresholdSweepPoint;
  completedCount: number;
  totalCount: number;
}

interface SweepCompleteEvent {
  type: "sweep_complete";
  parameter: string;
  sweepType: "numeric" | "categorical";
  points: ThresholdSweepPoint[];
}

type SweepEvent = SweepPointEvent | SweepCompleteEvent;

interface ThresholdSweepProgress {
  point: ThresholdSweepPoint;
  completedCount: number;
  totalCount: number;
}

interface ThresholdSweepCallbacks {
  onPoint: (progress: ThresholdSweepProgress) => void;
  onComplete: (result: ThresholdSweepResult) => void;
  onError: (error: Error) => void;
}

export async function streamThresholdSweep(
  experimentId: string,
  request: SweepRequest,
  callbacks: ThresholdSweepCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const url = buildUrl(`/api/v1/experiments/${experimentId}/threshold-sweep`);
  try {
    for await (const event of streamTypedEvents<SweepEvent>(url, {
      method: "POST",
      body: request,
      ...(signal !== undefined ? { signal } : {}),
    })) {
      if (event.type === "sweep_point") {
        callbacks.onPoint({
          point: event.point,
          completedCount: event.completedCount,
          totalCount: event.totalCount,
        });
      } else {
        callbacks.onComplete({
          parameter: event.parameter,
          sweepType: event.sweepType,
          points: event.points,
        });
      }
    }
  } catch (err) {
    callbacks.onError(err instanceof Error ? err : new Error(String(err)));
  }
}
