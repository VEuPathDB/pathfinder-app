import { queryOptions } from "@tanstack/react-query";
import type {
  GeneSet,
  VdiPublication,
  VdiPublicationRequest,
  VdiPublicationStatus,
} from "@pathfinder/shared";
import { geneSetResponseSchema } from "@pathfinder/shared/generated/zod/geneSetResponseSchema";
import { vdiPublicationSchema } from "@pathfinder/shared/generated/zod/vdiPublicationSchema";
import { vdiPublicationStatusSchema } from "@pathfinder/shared/generated/zod/vdiPublicationStatusSchema";
import { z } from "zod";

import { queryKeyPrefixes } from "@/lib/query/keys";
import { requestJson, requestVoid } from "./http";

const GeneSetListSchema = z.array(geneSetResponseSchema);

/** The researcher's gene sets, on one site when `siteId` names one. */
export async function listGeneSets(siteId?: string): Promise<GeneSet[]> {
  return await requestJson(
    GeneSetListSchema,
    "/api/v1/gene-sets",
    siteId != null && siteId !== "" ? { query: { siteId } } : {},
  );
}

export function geneSetsListOptions(siteId: string) {
  return queryOptions({
    queryKey: [...queryKeyPrefixes.geneSets, "list", siteId] as const,
    queryFn: () => listGeneSets(siteId),
  });
}

export async function deleteGeneSet(geneSetId: string): Promise<void> {
  await requestVoid(`/api/v1/gene-sets/${encodeURIComponent(geneSetId)}`, {
    method: "DELETE",
  });
}

/** Publish a gene set as a user dataset in the researcher's VEuPathDB workspace. */
export async function publishGeneSetToVdi(
  geneSetId: string,
  req: VdiPublicationRequest,
): Promise<VdiPublication> {
  return await requestJson(
    vdiPublicationSchema,
    `/api/v1/gene-sets/${encodeURIComponent(geneSetId)}/vdi-publication`,
    { method: "POST", body: req },
  );
}

/** Where a published gene set stands on the site that holds it. */
export async function getGeneSetVdiPublication(
  geneSetId: string,
): Promise<VdiPublicationStatus> {
  return await requestJson(
    vdiPublicationStatusSchema,
    `/api/v1/gene-sets/${encodeURIComponent(geneSetId)}/vdi-publication`,
  );
}
