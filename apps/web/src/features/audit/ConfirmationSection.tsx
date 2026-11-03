import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { Fact } from "@pathfinder/shared/generated/types/Fact";
import type { FindingView } from "@pathfinder/shared/generated/types/FindingView";

import { EvidenceRegion } from "./RelativesSection";

export function ConfirmationSection({
  finding,
  evidence,
  facts,
  words,
}: {
  finding: FindingView;
  evidence: EvidenceView;
  facts: readonly Fact[];
  words: AuditWords;
}) {
  return (
    <EvidenceRegion
      evidence={evidence}
      facts={facts}
      words={words}
      lead={finding.verdictText}
    />
  );
}
