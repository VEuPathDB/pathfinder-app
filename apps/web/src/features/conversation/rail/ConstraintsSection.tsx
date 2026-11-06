"use client";

import type { GroundedConstraint } from "@pathfinder/shared/generated/types/GroundedConstraint";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

import { type Tone } from "@/features/conversation/rail/statusTone";

import { constraintSentences } from "./constraintSentences";
import { LedgerSection, StatusPill } from "./LedgerPanelPrimitives";

const STATUS_TONE: Record<GroundedConstraint["status"], Tone> = {
  grounded: "good",
  provisional: "neutral",
  substituted: "warn",
  ungroundable: "bad",
  not_verified: "neutral",
};

const STATUS_WORDS: Record<GroundedConstraint["status"], string> = {
  grounded: "grounded",
  provisional: "provisional",
  substituted: "substituted",
  ungroundable: "ungroundable",
  not_verified: "not verified",
};

function ConstraintRow({ entry }: { entry: GroundedConstraint }) {
  const { constraint } = entry;
  const realized = entry.realizedValue ?? "-";
  return (
    <div className="ml-1 border-l border-border pl-2 text-[0.6875rem]">
      <div className="flex items-center justify-between gap-2">
        <span>
          {constraint.label}
          {constraint.source === "user_explicit" ? " *" : ""}
        </span>
        <StatusPill
          text={STATUS_WORDS[entry.status]}
          tone={STATUS_TONE[entry.status]}
        />
      </div>
      <p className="text-muted-foreground">
        requested {constraint.requestedValue} -&gt; {realized}
      </p>
      {entry.note != null && entry.note !== "" && (
        <p className="italic text-muted-foreground">{entry.note}</p>
      )}
    </div>
  );
}

export function ConstraintsSection({
  constraints,
}: {
  constraints: InvestigationLedger["constraints"];
}) {
  const grounded = constraints?.grounded ?? [];
  const sentences = constraintSentences(grounded);
  return (
    <LedgerSection title="Constraints">
      {sentences.length > 0 && (
        <p
          data-testid="constraints-summary"
          className="ml-1 pl-2 text-xs leading-relaxed text-foreground"
        >
          {sentences.join(" ")}
        </p>
      )}
      {grounded.length === 0 ? (
        <p className="ml-1 pl-2 text-[0.6875rem] italic text-muted-foreground">none</p>
      ) : (
        grounded.map((entry) => (
          <ConstraintRow
            key={`${entry.constraint.kind}:${entry.constraint.label}`}
            entry={entry}
          />
        ))
      )}
    </LedgerSection>
  );
}
