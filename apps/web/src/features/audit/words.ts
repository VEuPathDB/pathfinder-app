import type { AuditRunSummaryPhaseEnumKey } from "@pathfinder/shared/generated/types/AuditRunSummary";
import type {
  EvidenceViewKindEnumKey,
  EvidenceViewStatusEnumKey,
} from "@pathfinder/shared/generated/types/EvidenceView";
import type {
  FindingViewCertaintyEnumKey,
  FindingViewCheckEnumKey,
  FindingViewErrorTypeEnumKey,
  FindingViewStatusEnumKey,
} from "@pathfinder/shared/generated/types/FindingView";
import type { GenomeUseSourceEnumKey } from "@pathfinder/shared/generated/types/GenomeUse";
import type {
  GenomeViewRoleEnumKey,
  GenomeViewStatusEnumKey,
} from "@pathfinder/shared/generated/types/GenomeView";
import type { ImportanceSourceEnumKey } from "@pathfinder/shared/generated/types/Importance";
import type { RunHaltKindEnumKey } from "@pathfinder/shared/generated/types/RunHalt";
import type { StageRecordNameEnumKey } from "@pathfinder/shared/generated/types/StageRecord";

export type Origin = "sample" | "unsampled" | "target";

export const CHECK_WORDS: Record<FindingViewCheckEnumKey, string> = {
  pseudogene_call: "Pseudogene calls on intact genes",
  selenoprotein_end: "Selenoproteins cut at their selenocysteine",
  gene_length: "Gene length against orthologs",
  gene_split: "One gene split into two models",
  gene_fusion: "Neighbouring genes fused into one model",
  strain_model: "Strain model against its reference",
  missing_gene: "Genes missing from the annotation",
  organelle_join: "Organelle genes at the circular join",
  intron_support: "Exon structure against RNA-seq",
};

export const ERROR_TYPE_WORDS: Record<FindingViewErrorTypeEnumKey, string> = {
  intact_gene_called_pseudogene: "Intact gene called a pseudogene",
  sec_read_as_stop: "Selenocysteine codon read as a stop",
  truncated_model: "Model too short",
  split_model: "One gene split into two models",
  over_extended_model: "Model too long",
  fused_model: "Two genes fused into one model",
  missing_gene: "Gene missing from the annotation",
  organelle_split_at_join: "Organelle gene split at the circular join",
  missing_exon: "Exon missing from the model",
  shifted_splice_site: "Splice site shifted",
  spurious_intron: "Intron the RNA-seq does not splice",
  unsupported_intron: "Intron with no RNA-seq support",
};

export const CERTAINTY_WORDS: Record<FindingViewCertaintyEnumKey, string> = {
  high: "High certainty",
  medium: "Medium certainty",
  low: "Low certainty",
};

export const FINDING_STATUS_WORDS: Record<FindingViewStatusEnumKey, string> = {
  screened: "Waiting to be checked",
  unsampled: "Not in the random sample",
  trying: "Being checked",
  confirmed: "Checked",
  failed: "Could not be checked",
  unreached: "Couldn't reach the site",
  unread: "Not read before the deadline",
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

export const HALT_WORDS: Record<RunHaltKindEnumKey, string> = {
  sign_in:
    "The audit needs your VEuPathDB sign-in. Sign in on the site, then resume it.",
  task_failed:
    "The audit task stopped on an error. Resume it to go on from the last unit it finished.",
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
