import type { ConfirmationEvidence } from "@pathfinder/shared/generated/types/ConfirmationEvidence";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { GeneEvidencePayload } from "@pathfinder/shared/generated/types/GeneEvidencePayload";

import { sampleDetail } from "./sampleRun";

export function strainConfirmation() {
  const { confirmation } = storedConfirmation(sampleDetail("strain_model"));
  if (confirmation.check !== "strain_model") throw new Error("not a strain check");
  return confirmation;
}

export function pseudogeneConfirmation() {
  const { confirmation } = storedConfirmation(sampleDetail("pseudogene_call"));
  if (confirmation.check !== "pseudogene_call") {
    throw new Error("not a pseudogene check");
  }
  return confirmation;
}

export function organelleConfirmation() {
  const { confirmation } = storedConfirmation(sampleDetail("organelle_join"));
  if (confirmation.check !== "organelle_join")
    throw new Error("not an organelle check");
  return confirmation;
}

export function storedConfirmation(detail: FindingDetail): ConfirmationEvidence {
  const payload = detail.evidence.find(
    (evidence) => evidence.kind === "confirmation",
  )?.payload;
  if (payload?.kind !== "confirmation") {
    throw new Error(`finding ${String(detail.finding.id)} stores no confirmation`);
  }
  return payload;
}

export function geneEvidenceOf(detail: FindingDetail): GeneEvidencePayload {
  const payload = detail.evidence.find(
    (evidence) => evidence.kind === "gene_evidence",
  )?.payload;
  if (payload?.kind !== "gene_evidence") {
    throw new Error(`finding ${String(detail.finding.id)} stores no gene evidence`);
  }
  return payload;
}
