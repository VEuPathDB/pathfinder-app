/**
 * Experiment API client — the evaluations a gene set has been through.
 */

import { queryOptions } from "@tanstack/react-query";
import type { Experiment } from "@pathfinder/shared";
import { experimentSchema } from "@pathfinder/shared/generated/zod/experimentSchema";
import { z } from "zod";

import { requestJson } from "@/lib/api/http";

const ExperimentListSchema = z.array(experimentSchema);

/** List the experiments this user ran against one gene set, newest first. */
export function listGeneSetExperiments(geneSetId: string): Promise<Experiment[]> {
  return requestJson(
    ExperimentListSchema,
    `/api/v1/gene-sets/${geneSetId}/experiments`,
  );
}

export function geneSetExperimentsOptions(geneSetId: string) {
  return queryOptions({
    queryKey: ["experiments", "by-gene-set", geneSetId] as const,
    queryFn: () => listGeneSetExperiments(geneSetId),
    enabled: geneSetId !== "",
  });
}
