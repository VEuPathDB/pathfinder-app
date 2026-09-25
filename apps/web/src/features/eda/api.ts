"use client";

import { queryOptions } from "@tanstack/react-query";
import type { ConversationEdaResponse } from "@pathfinder/shared/generated/types/ConversationEdaResponse";
import type { EdaAnalysisPatchResponse } from "@pathfinder/shared/generated/types/EdaAnalysisPatchResponse";
import type { EdaOwnDatasetListResponse } from "@pathfinder/shared/generated/types/EdaOwnDatasetListResponse";
import type { EdaStudyListResponse } from "@pathfinder/shared/generated/types/EdaStudyListResponse";
import type { EdaVizRequest } from "@pathfinder/shared/generated/types/EdaVizRequest";
import type { EdaVizResponse } from "@pathfinder/shared/generated/types/EdaVizResponse";
import type { PatchConversationEdaMutationRequest } from "@pathfinder/shared/generated/types/PatchConversationEda";
import { conversationEdaResponseSchema } from "@pathfinder/shared/generated/zod/conversationEdaResponseSchema";
import { edaAnalysisPatchResponseSchema } from "@pathfinder/shared/generated/zod/edaAnalysisPatchResponseSchema";
import { edaOwnDatasetListResponseSchema } from "@pathfinder/shared/generated/zod/edaOwnDatasetListResponseSchema";
import { edaStudyListResponseSchema } from "@pathfinder/shared/generated/zod/edaStudyListResponseSchema";
import { edaVizResponseSchema } from "@pathfinder/shared/generated/zod/edaVizResponseSchema";

import { requestJson } from "@/lib/api/http";

/** The action union the conversation PATCH takes: bind, export-step, unbind. */
export type EdaAnalysisPatch = PatchConversationEdaMutationRequest;

/** A dataset id is unique within a site, so every EDA read names its site. */
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

/** The researcher's uploads on one site, read from VEuPathDB each time the key is stale. */
export function ownDatasetsOptions(siteId: string) {
  return queryOptions({
    queryKey: ["eda", "datasets", siteId] as const,
    queryFn: (): Promise<EdaOwnDatasetListResponse> =>
      requestJson(edaOwnDatasetListResponseSchema, "/api/v1/eda/datasets", {
        query: { siteId },
      }),
  });
}
