"use client";

import { useQuery } from "@tanstack/react-query";
import type { Experiment } from "@pathfinder/shared";

import { geneSetExperimentsOptions } from "@/features/workbench/api/experiments";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";

/**
 * The completed evaluation the active gene set holds, or null.
 *
 * A run this tab has just finished answers first, because its row reaches the
 * database outside the turn that created it. Every other reader answers from
 * the stored experiments, so the set keeps its evaluation across a reload.
 */
export function useActiveSetExperiment(): Experiment | null {
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const lastExperiment = useWorkbenchStore((s) => s.lastExperiment);
  const lastExperimentSetId = useWorkbenchStore((s) => s.lastExperimentSetId);

  const { data } = useQuery(geneSetExperimentsOptions(activeSetId ?? ""));

  if (activeSetId == null) return null;
  if (lastExperiment != null && lastExperimentSetId === activeSetId) {
    return lastExperiment;
  }
  return (data ?? []).find((exp) => exp.status === "completed") ?? null;
}
