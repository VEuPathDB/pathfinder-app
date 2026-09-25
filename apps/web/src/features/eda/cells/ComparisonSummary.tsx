"use client";

import type { EdaComputeSummary } from "@pathfinder/shared/generated/types/EdaComputeSummary";

import { useEdaStore } from "@/state/eda";

import { CellShell } from "./CellShell";

const MUTED = "text-xs text-muted-foreground";

function comparisonSentence(compute: EdaComputeSummary): string {
  return `${compute.method} compares ${compute.groupA.join(", ")} (group A) with ${compute.groupB.join(", ")} (group B) on ${compute.comparatorVariable}, reading ${compute.valueVariable} per ${compute.identifierVariable}.`;
}

/** The comparison the analysis holds, as one sentence. The site's notebook edits it. */
export function ComparisonSummary() {
  const compute = useEdaStore((s) => s.analysis?.compute ?? null);
  return (
    <CellShell title="Comparison" subtitle={null} testId="eda-comparison-summary">
      {compute === null ? (
        <p data-testid="eda-comparison-none" className={MUTED}>
          No comparison has run on this analysis. Ask for one in the conversation.
        </p>
      ) : (
        <p data-testid="eda-comparison-sentence" className="text-xs">
          {comparisonSentence(compute)}
        </p>
      )}
    </CellShell>
  );
}
