"use client";

import { queryOptions } from "@tanstack/react-query";
import type { EdaDistributionSeries } from "@pathfinder/shared";
import type { ConversationEdaResponse } from "@pathfinder/shared/generated/types/ConversationEdaResponse";
import type { EdaAnalysisPatchResponse } from "@pathfinder/shared/generated/types/EdaAnalysisPatchResponse";
import type { EdaCountRequest } from "@pathfinder/shared/generated/types/EdaCountRequest";
import type { EdaCountResponse } from "@pathfinder/shared/generated/types/EdaCountResponse";
import type { EdaDistributionRequest } from "@pathfinder/shared/generated/types/EdaDistributionRequest";
import type { EdaStudyDetailResponse } from "@pathfinder/shared/generated/types/EdaStudyDetailResponse";
import type { EdaStudyListResponse } from "@pathfinder/shared/generated/types/EdaStudyListResponse";
import type { EdaVizRequest } from "@pathfinder/shared/generated/types/EdaVizRequest";
import type { EdaVizResponse } from "@pathfinder/shared/generated/types/EdaVizResponse";
import type { PatchConversationEdaMutationRequest } from "@pathfinder/shared/generated/types/PatchConversationEda";
import { conversationEdaResponseSchema } from "@pathfinder/shared/generated/zod/conversationEdaResponseSchema";
import { edaAnalysisPatchResponseSchema } from "@pathfinder/shared/generated/zod/edaAnalysisPatchResponseSchema";
import { edaCountResponseSchema } from "@pathfinder/shared/generated/zod/edaCountResponseSchema";
import { edaDistributionSeriesSchema } from "@pathfinder/shared/generated/zod/edaDistributionSeriesSchema";
import { edaStudyDetailResponseSchema } from "@pathfinder/shared/generated/zod/edaStudyDetailResponseSchema";
import { edaStudyListResponseSchema } from "@pathfinder/shared/generated/zod/edaStudyListResponseSchema";
import { edaVizResponseSchema } from "@pathfinder/shared/generated/zod/edaVizResponseSchema";

import { requestJson } from "@/lib/api/http";

/** The five-way action union the conversation PATCH takes. */
export type EdaAnalysisPatch = PatchConversationEdaMutationRequest;

/** A dataset id is unique within a site, so every EDA read names its site. */
export type EdaCountArgs = EdaCountRequest & { siteId: string };
export type EdaDistributionArgs = EdaDistributionRequest & { siteId: string };
export type EdaVizArgs = EdaVizRequest & { siteId: string; conversationId: string };

const MIN_STUDY_QUERY_LENGTH = 2;

export async function searchEdaStudies(
  siteId: string,
  query: string,
): Promise<EdaStudyListResponse> {
  return await requestJson(edaStudyListResponseSchema, "/api/v1/eda/studies", {
    query: { siteId, q: query },
  });
}

export function edaStudySearchOptions(siteId: string, query: string) {
  return queryOptions({
    queryKey: ["eda", "studies", siteId, query] as const,
    queryFn: () => searchEdaStudies(siteId, query),
    enabled: query.trim().length >= MIN_STUDY_QUERY_LENGTH,
    staleTime: 60_000,
  });
}

export async function getEdaStudyDetail(
  siteId: string,
  datasetId: string,
): Promise<EdaStudyDetailResponse> {
  return await requestJson(
    edaStudyDetailResponseSchema,
    `/api/v1/eda/studies/${datasetId}`,
    { query: { siteId } },
  );
}

export function edaStudyDetailOptions(siteId: string, datasetId: string) {
  return queryOptions({
    queryKey: ["eda", "study", siteId, datasetId] as const,
    queryFn: () => getEdaStudyDetail(siteId, datasetId),
    staleTime: Infinity,
  });
}

export async function countEdaSubset(args: EdaCountArgs): Promise<EdaCountResponse> {
  const { siteId, ...body } = args;
  return await requestJson(edaCountResponseSchema, "/api/v1/eda/count", {
    method: "POST",
    query: { siteId },
    body,
  });
}

export async function edaDistribution(
  args: EdaDistributionArgs,
): Promise<EdaDistributionSeries> {
  const { siteId, ...body } = args;
  return await requestJson(edaDistributionSeriesSchema, "/api/v1/eda/distribution", {
    method: "POST",
    query: { siteId },
    body,
  });
}

export async function edaViz(args: EdaVizArgs): Promise<EdaVizResponse> {
  const { siteId, conversationId, ...body } = args;
  return await requestJson(edaVizResponseSchema, "/api/v1/eda/viz", {
    method: "POST",
    query: { siteId, conversationId },
    body,
  });
}

export async function getConversationEda(
  conversationId: string,
): Promise<ConversationEdaResponse> {
  return await requestJson(
    conversationEdaResponseSchema,
    `/api/v1/conversations/${conversationId}/eda`,
  );
}

export function conversationEdaOptions(conversationId: string) {
  return queryOptions({
    queryKey: ["conversations", conversationId, "eda"] as const,
    queryFn: () => getConversationEda(conversationId),
    staleTime: 0,
  });
}

export async function patchConversationEda(
  conversationId: string,
  body: EdaAnalysisPatch,
): Promise<EdaAnalysisPatchResponse> {
  return await requestJson(
    edaAnalysisPatchResponseSchema,
    `/api/v1/conversations/${conversationId}/eda`,
    { method: "PATCH", body },
  );
}
