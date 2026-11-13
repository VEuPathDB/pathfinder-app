import type { EvidenceCard, SampledGene, Strategy } from "@strategist/shared";
import type { GroundedConstraint } from "@strategist/shared/generated/types/GroundedConstraint";
import type { NodeResult } from "@strategist/shared/generated/types/NodeResult";
import type { VerificationDigest } from "@strategist/shared/generated/types/VerificationDigest";
import type { VerificationSection } from "@strategist/shared/generated/types/VerificationSection";

import { phaseLabel } from "@/lib/models/phaseRoles";
import { countNoun } from "@/lib/utils/countNoun";
import { countOf } from "@/lib/utils/countOf";

import type { LedgerView } from "./readLedger";

export type ReviewTone = "good" | "warn" | "bad" | "neutral";
export type VerdictKind =
  | "working"
  | "build_failed"
  | "stale"
  | "gaps"
  | "failed"
  | "answered"
  | "unchecked"
  | "unbuilt"
  | "empty";

export interface Verdict {
  kind: VerdictKind;
  tone: ReviewTone;
  title: string;
  detail: string | null;
}

export type RequirementStatus = "met" | "different" | "missed" | "unchecked";

export interface RequirementRow {
  key: string;
  label: string;
  requested: string;
  status: RequirementStatus;
  note: string | null;
}

export interface BuildProblem {
  key: string;
  step: string;
  status: "failed" | "zero";
  sentence: string;
}

export interface SpotCheck {
  yes: number;
  unclear: number;
  no: number;
  genes: SampledGene[];
}

export interface Choice {
  key: string;
  param: string;
  value: string;
  source: "chosen" | "default";
  sentence: string;
}

export interface ReviewModel {
  question: string | null;
  verdict: Verdict;
  requirements: RequirementRow[];
  buildProblems: BuildProblem[];
  spotCheck: SpotCheck | null;
  choices: Choice[];
  caveats: string[];
}

export interface ReviewInput {
  ledger: LedgerView | null;
  card: EvidenceCard | null;
  superseded: boolean;
  runningPhase: string | null;
  strategy: Strategy | null;
  rootCount: number | null;
}

export const REQUIREMENT_WORDS: Record<RequirementStatus, string> = {
  met: "Met",
  different: "Answered differently",
  missed: "Not met",
  unchecked: "Not checked",
};

const REQUIREMENT_STATUS: Record<GroundedConstraint["status"], RequirementStatus> = {
  grounded: "met",
  substituted: "different",
  ungroundable: "missed",
  provisional: "unchecked",
  not_verified: "unchecked",
};

const COMBINE_SEARCH = "__combine__";

type Caveat = NonNullable<VerificationSection["caveats"]>[number];
type Gap = NonNullable<VerificationDigest["gaps"]>[number];

function present(text: string | null | undefined): string | null {
  return text == null || text.trim() === "" ? null : text;
}

function question(ledger: LedgerView | null): string | null {
  const spec = ledger?.frame?.spec;
  return (
    present(ledger?.userIntent?.inferredGoal) ??
    present(spec?.interpretedGoal) ??
    present(spec?.goal)
  );
}

function requirements(ledger: LedgerView | null): RequirementRow[] {
  return (ledger?.constraints?.grounded ?? [])
    .filter((entry) => entry.constraint.source === "user_explicit")
    .map((entry, index) => ({
      key: `${index}:${entry.constraint.label}`,
      label: entry.constraint.label,
      requested: entry.constraint.requestedValue,
      status: REQUIREMENT_STATUS[entry.status],
      note: present(entry.note),
    }));
}

function stepName(node: NodeResult, strategy: Strategy | null): string {
  const step = strategy?.steps.find((s) => s.id === node.nodeId);
  const shown = present(step?.displayName);
  if (shown !== null) return shown;
  return node.searchName === COMBINE_SEARCH ? "Combine" : node.searchName;
}

function buildProblems(
  ledger: LedgerView | null,
  strategy: Strategy | null,
): BuildProblem[] {
  return (ledger?.build?.nodeResults ?? []).flatMap((node): BuildProblem[] => {
    if (node.status === "ok") return [];
    const step = strategy?.steps.find((s) => s.id === node.nodeId);
    return [
      {
        key: node.nodeId,
        step: stepName(node, strategy),
        status: node.status,
        sentence:
          node.status === "failed"
            ? (present(node.error) ?? "The site refused this step.")
            : `Returned 0 ${countNoun(step?.recordType, 0)}.`,
      },
    ];
  });
}

function spotCheck(card: EvidenceCard | null): SpotCheck | null {
  const genes = card?.review?.sampledGenes ?? [];
  if (genes.length === 0) return null;
  const count = (fit: SampledGene["fits"]) =>
    genes.filter((g) => g.fits === fit).length;
  return { yes: count("yes"), unclear: count("unclear"), no: count("no"), genes };
}

function isChoice(
  caveat: Caveat,
): caveat is Extract<Caveat, { kind: "assumed_value" | "chosen_among" }> {
  return caveat.kind === "assumed_value" || caveat.kind === "chosen_among";
}

function choices(caveats: readonly Caveat[]): Choice[] {
  return caveats.filter(isChoice).map((caveat) => ({
    key: `${caveat.criterionId}:${caveat.paramDisplayName}`,
    param: caveat.paramDisplayName,
    value: caveat.value,
    source: caveat.source,
    sentence: caveat.sentence,
  }));
}

function answeredDetail(
  card: EvidenceCard | null,
  strategy: Strategy | null,
  rootCount: number | null,
): string | null {
  const root = strategy?.steps.find((s) => s.id === strategy.rootStepId);
  const parts: string[] = [];
  if (rootCount !== null) {
    parts.push(
      `${rootCount.toLocaleString()} ${countNoun(root?.recordType, rootCount)}`,
    );
  }
  if (card !== null) {
    const drifted = card.steps.filter((step) => step.drifted).length;
    if (card.siteRead !== "read") parts.push("the site did not answer");
    else if (drifted > 0)
      parts.push(`${countOf(drifted, "count", "counts")} changed on the site`);
    else parts.push("counts match the site");
  }
  return parts.length === 0 ? null : parts.join(" · ");
}

function verdict(
  input: ReviewInput,
  problems: readonly BuildProblem[],
  gaps: readonly Gap[],
): Verdict {
  const { ledger, card, superseded, runningPhase, strategy } = input;
  const verification = ledger?.verification;
  if (runningPhase !== null) {
    return {
      kind: "working",
      tone: "neutral",
      title: `Working: ${phaseLabel(runningPhase)}`,
      detail: null,
    };
  }
  const failed = problems.find((p) => p.status === "failed");
  if (ledger?.build?.succeeded === false && failed !== undefined) {
    return {
      kind: "build_failed",
      tone: "bad",
      title: "The build failed",
      detail: failed.sentence,
    };
  }
  if (superseded) {
    return {
      kind: "stale",
      tone: "neutral",
      title: "The strategy changed after the last check",
      detail: "Ask for a new check to update this review.",
    };
  }
  if (verification?.complete === true && gaps.length > 0) {
    return {
      kind: "gaps",
      tone: "warn",
      title: `${countOf(gaps.length, "part", "parts")} of your question not answered`,
      detail: null,
    };
  }
  if (verification?.complete === true && !verification.successful) {
    return {
      kind: "failed",
      tone: "bad",
      title: "The check did not pass",
      detail: present(verification.digest?.reason),
    };
  }
  if (verification?.complete === true) {
    return {
      kind: "answered",
      tone: "good",
      title: "The strategy answers your question",
      detail: answeredDetail(card, strategy, input.rootCount),
    };
  }
  if ((strategy?.steps.length ?? 0) > 0) {
    return {
      kind: "unchecked",
      tone: "neutral",
      title: "Built, not checked yet",
      detail: null,
    };
  }
  if (ledger !== null) {
    return { kind: "unbuilt", tone: "neutral", title: "Not built yet", detail: null };
  }
  return {
    kind: "empty",
    tone: "neutral",
    title: "Nothing to review yet",
    detail: "Ask a question and its plan, build and check appear here.",
  };
}

export function reviewModel(input: ReviewInput): ReviewModel {
  const verification = input.ledger?.verification;
  const caveats = verification?.caveats ?? [];
  const gaps = verification?.digest?.gaps ?? [];
  const problems = buildProblems(input.ledger, input.strategy);
  return {
    question: question(input.ledger),
    verdict: verdict(input, problems, gaps),
    requirements: requirements(input.ledger),
    buildProblems: problems,
    spotCheck: spotCheck(input.card),
    choices: choices(caveats),
    caveats: [
      ...caveats.filter((caveat) => !isChoice(caveat)).map((caveat) => caveat.sentence),
      ...gaps.map((gap) => gap.sentence),
    ],
  };
}
