/**
 * What an EDA spec reads from the api: the studies a site lists, the analysis a
 * conversation holds and the volcano the site draws for it, with the sentences
 * the thread and the tab print from them.
 */

import { expect } from "@playwright/test";
import type { EdaAnalysisState, EdaEntityCount } from "@pathfinder/shared";
import type { ConversationEdaResponse } from "@pathfinder/shared/generated/types/ConversationEdaResponse";
import type { EdaComparison } from "@pathfinder/shared/generated/types/EdaComparison";
import type { EdaComputeSummary } from "@pathfinder/shared/generated/types/EdaComputeSummary";
import type { EdaStudyListResponse } from "@pathfinder/shared/generated/types/EdaStudyListResponse";
import type { EdaStudySummaryResponse } from "@pathfinder/shared/generated/types/EdaStudySummaryResponse";
import type { EdaVizResponse } from "@pathfinder/shared/generated/types/EdaVizResponse";

import type { ApiClient } from "./api-client";
import { printed } from "./site-reads";

/** The WDK search a step exported from a volcano runs. */
export const EDA_VIZ_SEARCH = "GenesByEdaVizWithCompute";

/** The studies the site lists with no query, as the picker's search route answers. */
export async function browseStudies(
  api: ApiClient,
  siteId: string,
): Promise<EdaStudySummaryResponse[]> {
  const resp = await api.get(`/api/v1/eda/studies?siteId=${siteId}&limit=100`, {
    timeout: 60_000,
  });
  expect(resp.status(), `studies on ${siteId}`).toBe(200);
  return ((await resp.json()) as EdaStudyListResponse).studies;
}

/** A study the site publishes itself, so the tab can open it. */
export async function ownStudy(
  api: ApiClient,
  siteId: string,
): Promise<EdaStudySummaryResponse> {
  const study = (await browseStudies(api, siteId)).find(
    (row) => row.notHere === null && row.canSubset,
  );
  if (study === undefined) throw new Error(`${siteId} lists no study of its own`);
  return study;
}

/** The analysis the conversation holds, or null when no study is open. */
export async function readAnalysis(
  api: ApiClient,
  conversationId: string,
): Promise<EdaAnalysisState | null> {
  const resp = await api.get(`/api/v1/conversations/${conversationId}/eda`);
  expect(resp.status(), `eda of ${conversationId}`).toBe(200);
  return ((await resp.json()) as ConversationEdaResponse).analysis;
}

/** The analysis the conversation holds; a conversation with none fails. */
export async function openAnalysis(
  api: ApiClient,
  conversationId: string,
): Promise<EdaAnalysisState> {
  const analysis = await readAnalysis(api, conversationId);
  if (analysis === null) throw new Error(`${conversationId} holds no analysis`);
  return analysis;
}

/** The comparison the analysis ran; an analysis with none fails. */
export function computeOf(analysis: EdaAnalysisState): EdaComputeSummary {
  const compute = analysis.compute ?? null;
  if (compute === null) throw new Error(`${analysis.analysisId} ran no comparison`);
  return compute;
}

/** The volcano the site draws for the conversation's analysis, at its stored cut. */
export async function readVolcano(
  api: ApiClient,
  siteId: string,
  conversationId: string,
): Promise<EdaVizResponse> {
  const resp = await api.post(
    `/api/v1/eda/viz?siteId=${siteId}&conversationId=${conversationId}`,
    { data: { chart: "volcano" }, timeout: 120_000 },
  );
  expect(resp.status(), `volcano of ${conversationId}`).toBe(200);
  return (await resp.json()) as EdaVizResponse;
}

/** One entity's count as the subset cell prints it, `8 of 12 Sample`. */
export function entityLine(entity: EdaEntityCount): string {
  const name =
    entity.entityDisplayName.length > 0 ? entity.entityDisplayName : entity.entityId;
  return `${printed(entity.count)} of ${printed(entity.unfilteredCount)} ${name}`;
}

/** The study card's caption: every entity's count, comma separated. */
export function entityCaption(analysis: EdaAnalysisState): string {
  return analysis.entityCounts.map(entityLine).join(", ");
}

/** The two groups under the thread's volcano. */
export function groupsLine(comparison: EdaComparison): string {
  return `Group A: ${comparison.groupA.join(", ")} - Group B: ${comparison.groupB.join(", ")}`;
}

/** The comparison cell's one sentence. */
export function comparisonSentence(compute: EdaComputeSummary): string {
  return `${compute.method} compares ${compute.groupA.join(", ")} (group A) with ${compute.groupB.join(", ")} (group B) on ${compute.comparatorVariable}, reading ${compute.valueVariable} per ${compute.identifierVariable}.`;
}

/** The cut the tab states above its volcano. */
export function cutSentence(viz: EdaVizResponse): string {
  const side = {
    upAndDown: "Higher in either group",
    upOnly: `Higher in ${viz.comparison.groupB.join(", ")}`,
    downOnly: `Higher in ${viz.comparison.groupA.join(", ")}`,
  }[viz.effectDirection];
  return `${side}, |effect size| >= ${String(viz.effectSizeThreshold)}, p <= ${String(viz.significanceThreshold)}`;
}

/** The tab's selection line when the cut selects every retained gene. */
export function selectionSentence(viz: EdaVizResponse): string {
  const n = viz.retainedPoints;
  return `${String(n)} ${n === 1 ? "gene" : "genes"} selected, ${String(n)} of ${String(viz.totalPoints)} retained by the comparison`;
}

/** The genes the thread's volcano retains, as its caption states them. */
export function retainedClause(viz: EdaVizResponse): string {
  return `${printed(viz.retainedPoints)} of ${printed(viz.totalPoints)} genes retained`;
}

/** The name a step exported from the volcano carries. */
export function exportedStepName(viz: EdaVizResponse): string {
  const a = viz.comparison.groupA.join(", ");
  const b = viz.comparison.groupB.join(", ");
  const kept = {
    upAndDown: `that differ between ${a} and ${b}`,
    upOnly: `higher in ${b} than in ${a}`,
    downOnly: `higher in ${a} than in ${b}`,
  }[viz.effectDirection];
  return `Genes ${kept}`;
}

/** The Studies rail's line under the study name. */
export function railStudyLine(analysis: EdaAnalysisState): string {
  const filters = analysis.numFilters;
  const computations = analysis.numComputations;
  return `${printed(filters)} ${filters === 1 ? "filter" : "filters"} - ${printed(computations)} ${computations === 1 ? "computation" : "computations"}`;
}
