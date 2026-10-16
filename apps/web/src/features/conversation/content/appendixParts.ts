import { DataControlTestResults } from "./parts/DataControlTestResults";
import { DataEdaAnalysisState } from "./parts/DataEdaAnalysisState";
import { DataEdaSubsetPreview } from "./parts/DataEdaSubsetPreview";
import { DataEvidenceCard } from "./parts/DataEvidenceCard";
import { DataFacts } from "./parts/DataFacts";
import { DataGraphSnapshot } from "./parts/DataGraphSnapshot";
import { DataMemoryRetrieved } from "./parts/DataMemoryRetrieved";
import { DataResearchSources } from "./parts/DataResearchSources";
import { DataStrategyLink } from "./parts/DataStrategyLink";
import { DataStrategyMeta } from "./parts/DataStrategyMeta";
import type { DataPartComponentMap } from "./dataPartComponentMap";

export const APPENDIX_KINDS = [
  "data-facts",
  "data-evidence-card",
  "data-control-test-results",
  "data-graph-snapshot",
  "data-strategy-link",
  "data-strategy-meta",
  "data-research.sources",
  "data-memory-retrieved",
  "data-eda.analysis-state",
  "data-eda.subset-preview",
] as const;

export type AppendixKind = (typeof APPENDIX_KINDS)[number];

export const appendixComponents: DataPartComponentMap<AppendixKind> = {
  "data-facts": DataFacts,
  "data-evidence-card": DataEvidenceCard,
  "data-control-test-results": DataControlTestResults,
  "data-graph-snapshot": DataGraphSnapshot,
  "data-strategy-link": DataStrategyLink,
  "data-strategy-meta": DataStrategyMeta,
  "data-research.sources": DataResearchSources,
  "data-memory-retrieved": DataMemoryRetrieved,
  "data-eda.analysis-state": DataEdaAnalysisState,
  "data-eda.subset-preview": DataEdaSubsetPreview,
};

export const SECTION_TITLES: Record<AppendixKind, string> = {
  "data-facts": "Strategy",
  "data-evidence-card": "Evidence",
  "data-control-test-results": "Control tests",
  "data-graph-snapshot": "Strategy updated",
  "data-strategy-link": "Strategy",
  "data-strategy-meta": "Strategy",
  "data-research.sources": "Sources",
  "data-memory-retrieved": "Recalled memories",
  "data-eda.analysis-state": "Analysis",
  "data-eda.subset-preview": "Subset",
};

export const LATEST_ONLY: ReadonlySet<AppendixKind> = new Set([
  "data-graph-snapshot",
  "data-strategy-link",
  "data-strategy-meta",
  "data-eda.analysis-state",
]);

export const FULL_WIDTH: ReadonlySet<AppendixKind> = new Set([
  "data-facts",
  "data-evidence-card",
  "data-control-test-results",
]);

export function isAppendixKind(kind: string): kind is AppendixKind {
  return (APPENDIX_KINDS as readonly string[]).includes(kind);
}
