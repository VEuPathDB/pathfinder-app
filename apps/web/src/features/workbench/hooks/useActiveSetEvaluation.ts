"use client";

import { useQuery } from "@tanstack/react-query";

import { geneSetExperimentsOptions } from "@/features/workbench/api/experiments";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import {
  setEvaluation,
  type SetEvaluation,
} from "@/features/workbench/components/setEvaluation";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";

/**
 * The completed evaluation the active gene set holds, read against the
 * membership that set holds now.
 *
 * A run this tab has just finished answers first, because its row reaches the
 * database outside the turn that created it. Every other reader answers from
 * the stored experiments, so the set keeps its evaluation across a reload.
 */
export function useActiveSetEvaluation(): SetEvaluation | null {
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const lastExperiment = useWorkbenchStore((s) => s.lastExperiment);
  const lastExperimentSetId = useWorkbenchStore((s) => s.lastExperimentSetId);
  const selectedSite = useSessionStore((s) => s.selectedSite);

  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const { data } = useQuery(geneSetExperimentsOptions(activeSetId ?? ""));

  if (activeSetId == null) return null;
  const experiment =
    lastExperiment != null && lastExperimentSetId === activeSetId
      ? lastExperiment
      : ((data ?? []).find((exp) => exp.status === "completed") ?? null);
  return setEvaluation(
    experiment,
    geneSets.find((gs) => gs.id === activeSetId),
  );
}
