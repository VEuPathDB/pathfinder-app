import type { UIMessage } from "ai";
import type { EdaAnalysisState } from "@pathfinder/shared";

const PART_TYPE = "data-eda.analysis-state";

function statePartsOf(messages: readonly UIMessage[]): EdaAnalysisState[] {
  const states: EdaAnalysisState[] = [];
  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type !== PART_TYPE || !("data" in part)) continue;
      states.push(part.data as EdaAnalysisState);
    }
  }
  return states;
}

function newestStateFor(
  messages: readonly UIMessage[],
  analysisId: string,
): EdaAnalysisState | undefined {
  return statePartsOf(messages)
    .filter((state) => state.analysisId === analysisId)
    .at(-1);
}

/** Whether this payload is the thread's newest state for its analysis. */
export function isNewestAnalysisState(
  messages: readonly UIMessage[],
  data: EdaAnalysisState,
): boolean {
  const last = newestStateFor(messages, data.analysisId);
  if (last === undefined) return true;
  return JSON.stringify(last) === JSON.stringify(data);
}

/** The study's display name for one analysis, read off the thread. */
export function studyNameFor(
  messages: readonly UIMessage[],
  analysisId: string,
): string {
  return newestStateFor(messages, analysisId)?.studyDisplayName ?? "";
}

export interface AnalysisSiteLink {
  siteId: string;
  href: string;
}

/** The site explorer page of one analysis, read off the thread. */
export function analysisSiteLinkFor(
  messages: readonly UIMessage[],
  analysisId: string,
): AnalysisSiteLink | null {
  const state = newestStateFor(messages, analysisId);
  if (state?.analysisUrl == null) return null;
  return { siteId: state.siteId, href: state.analysisUrl };
}
