/**
 * Gene set API client — CRUD and set-operation endpoints.
 */

import { queryOptions } from "@tanstack/react-query";
import type { EnrichmentResult, GeneSet } from "@pathfinder/shared";
import { geneSetResponseSchema } from "@pathfinder/shared/generated/zod/geneSetResponseSchema";
import { z } from "zod";

import { requestJson, requestVoid } from "@/lib/api/http";
import type { CreateGeneSetRequest } from "@pathfinder/shared/generated/types/CreateGeneSetRequest";
import type { GeneSetEnrichRequest } from "@pathfinder/shared/generated/types/GeneSetEnrichRequest";
import type { SetOperationRequest } from "@pathfinder/shared/generated/types/SetOperationRequest";
import type {
  VdiPublication,
  VdiPublicationRequest,
  VdiPublicationStatus,
} from "@pathfinder/shared";
import { vdiPublicationSchema } from "@pathfinder/shared/generated/zod/vdiPublicationSchema";
import { vdiPublicationStatusSchema } from "@pathfinder/shared/generated/zod/vdiPublicationStatusSchema";
import { enrichmentResultSchema } from "@pathfinder/shared/generated/zod/enrichmentResultSchema";

const EnrichmentResultListSchema = z.array(enrichmentResultSchema);

const GeneSetListSchema = z.array(geneSetResponseSchema);

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Create a new gene set. */
export function createGeneSet(req: CreateGeneSetRequest): Promise<GeneSet> {
  return requestJson(geneSetResponseSchema, "/api/v1/gene-sets", {
    method: "POST",
    body: req,
  });
}

/** List gene sets, optionally filtered by site. */
export function listGeneSets(siteId?: string): Promise<GeneSet[]> {
  return requestJson(GeneSetListSchema, "/api/v1/gene-sets", {
    ...(siteId != null && siteId !== "" ? { query: { siteId } } : {}),
  });
}

/** Delete a gene set by ID. */
export function deleteGeneSet(id: string): Promise<void> {
  return requestVoid(`/api/v1/gene-sets/${id}`, {
    method: "DELETE",
  });
}

/** Replace a gene set's genes with what its source strategy holds now. */
export function retakeGeneSet(id: string): Promise<GeneSet> {
  return requestJson(geneSetResponseSchema, `/api/v1/gene-sets/${id}/retake`, {
    method: "POST",
  });
}

/** Perform a set operation (intersect, union, minus) across gene sets. */
export function performSetOperation(req: SetOperationRequest): Promise<GeneSet> {
  return requestJson(geneSetResponseSchema, "/api/v1/gene-sets/operations", {
    method: "POST",
    body: req,
  });
}

/** Publish a gene set as a user dataset in the researcher's VEuPathDB workspace. */
export function publishGeneSetToVdi(
  id: string,
  req: VdiPublicationRequest,
): Promise<VdiPublication> {
  return requestJson(vdiPublicationSchema, `/api/v1/gene-sets/${id}/vdi-publication`, {
    method: "POST",
    body: req,
  });
}

/** Read where a published gene set stands on the site that holds it. */
export function getGeneSetVdiPublication(id: string): Promise<VdiPublicationStatus> {
  return requestJson(
    vdiPublicationStatusSchema,
    `/api/v1/gene-sets/${id}/vdi-publication`,
  );
}

/** Run enrichment analysis on a gene set. */
export function enrichGeneSet(
  id: string,
  types: GeneSetEnrichRequest["enrichmentTypes"],
): Promise<EnrichmentResult[]> {
  const body: GeneSetEnrichRequest = { enrichmentTypes: types };
  return requestJson(EnrichmentResultListSchema, `/api/v1/gene-sets/${id}/enrich`, {
    method: "POST",
    body,
  });
}

// ---------------------------------------------------------------------------
// Strategy-sourced gene set creation
// ---------------------------------------------------------------------------

export interface CreateFromStrategyArgs {
  name: string;
  siteId: string;
  wdkStrategyId: number;
  wdkStepId?: number;
  searchName?: string;
  recordType?: string;
  parameters?: CreateGeneSetRequest["parameters"];
  geneIds?: string[];
}

/**
 * Create a gene set from a built WDK strategy.
 *
 * Sends the strategy metadata along with whatever gene IDs are available.
 * When `geneIds` is empty the backend will still persist the set; enrichment
 * can use the `wdkStepId` directly.
 */
export function createGeneSetFromStrategy(
  args: CreateFromStrategyArgs,
): Promise<GeneSet> {
  const req: CreateGeneSetRequest = {
    name: args.name,
    source: "strategy",
    geneIds: args.geneIds ?? [],
    siteId: args.siteId,
    wdkStrategyId: args.wdkStrategyId,
  };
  if (args.wdkStepId != null) req.wdkStepId = args.wdkStepId;
  if (args.searchName != null) req.searchName = args.searchName;
  if (args.recordType != null) req.recordType = args.recordType;
  if (args.parameters != null) req.parameters = args.parameters;
  return createGeneSet(req);
}

export function geneSetsListOptions(siteId: string) {
  return queryOptions({
    queryKey: ["gene-sets", "list", siteId] as const,
    queryFn: () => listGeneSets(siteId),
  });
}
