import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";

export function EvidenceNote({
  evidence,
  words,
}: {
  evidence: EvidenceView;
  words: AuditWords;
}) {
  const stated = words.evidenceStatuses[evidence.status];
  const failed = evidence.status === "failed" && evidence.message !== null;
  return (
    <p className="mt-1 text-sm">{failed ? `${stated}: ${evidence.message}` : stated}</p>
  );
}
