import { describe, expect, it } from "vitest";
import { auditRunSummaryPhaseEnum } from "@pathfinder/shared/generated/types/AuditRunSummary";
import {
  evidenceViewKindEnum,
  evidenceViewStatusEnum,
} from "@pathfinder/shared/generated/types/EvidenceView";
import { findingViewCertaintyEnum } from "@pathfinder/shared/generated/types/FindingView";
import { genomeUseSourceEnum } from "@pathfinder/shared/generated/types/GenomeUse";
import {
  genomeViewRoleEnum,
  genomeViewStatusEnum,
} from "@pathfinder/shared/generated/types/GenomeView";
import { importanceSourceEnum } from "@pathfinder/shared/generated/types/Importance";
import { stageRecordNameEnum } from "@pathfinder/shared/generated/types/StageRecord";

import * as words from "./words";

describe("audit words", () => {
  it("has a phrase with no internal name for every value the page names", () => {
    const phrases = [
      ...Object.values(findingViewCertaintyEnum).map(
        (key) => words.CERTAINTY_WORDS[key],
      ),
      ...Object.values(genomeViewStatusEnum).map(
        (key) => words.GENOME_STATUS_WORDS[key],
      ),
      ...Object.values(genomeViewRoleEnum).map((key) => words.ROLE_WORDS[key]),
      ...Object.values(evidenceViewStatusEnum).map(
        (key) => words.EVIDENCE_STATUS_WORDS[key],
      ),
      ...Object.values(evidenceViewKindEnum).map(
        (key) => words.EVIDENCE_KIND_WORDS[key],
      ),
      ...Object.values(stageRecordNameEnum).map((key) => words.STAGE_WORDS[key]),
      ...Object.values(importanceSourceEnum).map((key) => words.IMPORTANCE_WORDS[key]),
      ...Object.values(genomeUseSourceEnum).map((key) => words.USE_WORDS[key]),
      ...Object.values(auditRunSummaryPhaseEnum).map((key) => words.PHASE_WORDS[key]),
      ...Object.values(words.ORIGIN_WORDS),
    ];
    expect(phrases.length).toBe(39);
    for (const phrase of phrases) expect(phrase).toMatch(/^[^_]+$/);
  });

  it("holds no table the API serves", () => {
    expect(Object.keys(words).sort()).toEqual([
      "CERTAINTY_WORDS",
      "EVIDENCE_KIND_WORDS",
      "EVIDENCE_STATUS_WORDS",
      "GENOME_STATUS_WORDS",
      "IMPORTANCE_WORDS",
      "ORIGIN_WORDS",
      "PHASE_WORDS",
      "ROLE_WORDS",
      "STAGE_WORDS",
      "USE_WORDS",
    ]);
  });

  it("names a certainty", () => {
    expect(words.CERTAINTY_WORDS).toEqual({
      high: "High certainty",
      medium: "Medium certainty",
      low: "Low certainty",
    });
  });

  it("names a genome's status and its role", () => {
    expect(words.GENOME_STATUS_WORDS).toEqual({
      pending: "Waiting to be read",
      trying: "Being read",
      collected: "Read",
      failed: "Could not be read",
      unreached: "Couldn't reach the site",
      unread: "Not read before the deadline",
    });
    expect(words.ROLE_WORDS).toEqual({
      audited: "Audited",
      comparison: "Compared against",
    });
  });

  it("names a piece of evidence's status and kind", () => {
    expect(words.EVIDENCE_STATUS_WORDS).toEqual({
      pending: "Waiting to be read",
      trying: "Being read",
      stored: "Read",
      failed: "Could not be read",
      unreached: "Couldn't reach the site",
      unread: "Not read before the deadline",
    });
    expect(words.EVIDENCE_KIND_WORDS).toEqual({
      confirmation: "What the genome's DNA shows",
      relatives: "Lengths in related genomes",
      gene_evidence: "What the site's gene records hold",
    });
  });

  it("names a stage and a run's phase", () => {
    expect(words.STAGE_WORDS).toEqual({
      collect: "Read the genomes",
      screen: "Find candidates",
      confirm: "Check candidates in the DNA",
      tie_break: "Weigh against relatives and gene records",
    });
    expect(words.PHASE_WORDS).toEqual({
      not_started: "Not started",
      queued: "Queued",
      running: "Running",
      halted: "Stopped",
      finished: "Finished",
    });
  });

  it("states where an importance and a genome's use come from", () => {
    expect(words.IMPORTANCE_WORDS).toEqual({
      cited: "a gene record cites a paper or holds a comment",
      uncited: "no gene record cites a paper or holds a comment",
      not_read: "the gene records were not read, so the lower value is used",
    });
    expect(words.USE_WORDS).toEqual({
      reference_strain: "the site marks this genome as its species' reference strain",
      other_strain:
        "the site does not mark this genome as its species' reference strain",
      unknown: "the reference-strain mark was not read, so the lower value is used",
      model_role: "the model's place in its strain pair",
    });
  });

  it("names where a finding came from", () => {
    expect(words.ORIGIN_WORDS).toEqual({
      sample: "Random sample",
      unsampled: "Not in the random sample",
      target: "Your gene target",
    });
  });
});
