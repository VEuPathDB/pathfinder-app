import type { AuditRunSummaryPhaseEnumKey } from "@pathfinder/shared/generated/types/AuditRunSummary";
import type {
  EvidenceViewKindEnumKey,
  EvidenceViewStatusEnumKey,
} from "@pathfinder/shared/generated/types/EvidenceView";
import type { FindingViewCertaintyEnumKey } from "@pathfinder/shared/generated/types/FindingView";
import type { GenomeUseSourceEnumKey } from "@pathfinder/shared/generated/types/GenomeUse";
import type {
  GenomeViewRoleEnumKey,
  GenomeViewStatusEnumKey,
} from "@pathfinder/shared/generated/types/GenomeView";
import type { ImportanceSourceEnumKey } from "@pathfinder/shared/generated/types/Importance";
import type { StageRecordNameEnumKey } from "@pathfinder/shared/generated/types/StageRecord";

export type Origin = "sample" | "unsampled" | "target";

export const CERTAINTY_WORDS: Record<FindingViewCertaintyEnumKey, string> = {
  high: "High certainty",
  medium: "Medium certainty",
  low: "Low certainty",
};

export const GENOME_STATUS_WORDS: Record<GenomeViewStatusEnumKey, string> = {
  pending: "Waiting to be read",
  trying: "Being read",
  collected: "Read",
  failed: "Could not be read",
  unreached: "Couldn't reach the site",
  unread: "Not read before the deadline",
};

export const EVIDENCE_STATUS_WORDS: Record<EvidenceViewStatusEnumKey, string> = {
  pending: "Waiting to be read",
  trying: "Being read",
  stored: "Read",
  failed: "Could not be read",
  unreached: "Couldn't reach the site",
  unread: "Not read before the deadline",
};

export const EVIDENCE_KIND_WORDS: Record<EvidenceViewKindEnumKey, string> = {
  confirmation: "What the genome's DNA shows",
  relatives: "Lengths in related genomes",
  gene_evidence: "What the site's gene records hold",
};

export const STAGE_WORDS: Record<StageRecordNameEnumKey, string> = {
  collect: "Read the genomes",
  screen: "Find candidates",
  confirm: "Check candidates in the DNA",
  tie_break: "Weigh against relatives and gene records",
};

export const ROLE_WORDS: Record<GenomeViewRoleEnumKey, string> = {
  audited: "Audited",
  comparison: "Compared against",
};

export const PHASE_WORDS: Record<AuditRunSummaryPhaseEnumKey, string> = {
  not_started: "Not started",
  queued: "Queued",
  running: "Running",
  halted: "Stopped",
  finished: "Finished",
};

export const IMPORTANCE_WORDS: Record<ImportanceSourceEnumKey, string> = {
  cited: "a gene record cites a paper or holds a comment",
  uncited: "no gene record cites a paper or holds a comment",
  not_read: "the gene records were not read, so the lower value is used",
};

export const USE_WORDS: Record<GenomeUseSourceEnumKey, string> = {
  reference_strain: "the site marks this genome as its species' reference strain",
  other_strain: "the site does not mark this genome as its species' reference strain",
  unknown: "the reference-strain mark was not read, so the lower value is used",
  model_role: "the model's place in its strain pair",
};

export const ORIGIN_WORDS: Record<Origin, string> = {
  sample: "Random sample",
  unsampled: "Not in the random sample",
  target: "Your gene target",
};
