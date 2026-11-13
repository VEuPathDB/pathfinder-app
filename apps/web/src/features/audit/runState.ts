import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";
import type { AuditWords } from "@strategist/shared/generated/types/AuditWords";
import type { StageRecord } from "@strategist/shared/generated/types/StageRecord";

import { joinWords, plural } from "./format";

const LEFT = ["unreached", "unread", "failed"] as const;

export interface LeftLine {
  status: (typeof LEFT)[number];
  genomes: number;
  findings: number;
  evidence: number;
}

function summed(
  rows: readonly { status: string; count: number }[],
  status: string,
): number {
  return rows
    .filter((row) => row.status === status)
    .reduce((sum, row) => sum + row.count, 0);
}

export function leftLines(view: AuditRunView): LeftLine[] {
  return LEFT.map((status) => ({
    status,
    genomes: view.genomes.filter((genome) => genome.status === status).length,
    findings: summed(view.counts, status),
    evidence: summed(view.evidence, status),
  })).filter((line) => line.genomes + line.findings + line.evidence > 0);
}

export function leftLineText(line: LeftLine, words: AuditWords): string {
  const parts = [
    ...(line.genomes > 0 ? [plural(line.genomes, "genome")] : []),
    ...(line.findings > 0 ? [plural(line.findings, "finding")] : []),
    ...(line.evidence > 0
      ? [plural(line.evidence, "piece of evidence", "pieces of evidence")]
      : []),
  ];
  return `${words.evidenceStatuses[line.status]}: ${joinWords(parts)}`;
}

export function stagesOf(view: AuditRunView): StageRecord[] {
  return view.stages.stages ?? [];
}

export function currentStage(view: AuditRunView): StageRecord | null {
  return stagesOf(view).find((stage) => stage.finished !== true) ?? null;
}
