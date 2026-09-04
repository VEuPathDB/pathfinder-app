"use client";

import type { GroundedConstraint } from "@pathfinder/shared/generated/types/GroundedConstraint";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

import { type Tone } from "@/features/conversation/rail/statusTone";

import {
  BoolBadge,
  LedgerRow,
  LedgerSection,
  StatusPill,
} from "./LedgerPanelPrimitives";

const STATUS_TONE: Record<GroundedConstraint["status"], Tone> = {
  grounded: "good",
  provisional: "neutral",
  substituted: "warn",
  ungroundable: "bad",
};

function ConstraintRow({ entry }: { entry: GroundedConstraint }) {
  const { constraint } = entry;
  const realized = entry.realizedValue ?? "—";
  return (
    <div className="ml-1 border-l border-border pl-2 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <span>
          {constraint.label}
          {constraint.source === "user_explicit" ? " *" : ""}
        </span>
        <StatusPill text={entry.status} tone={STATUS_TONE[entry.status]} />
      </div>
      <p className="text-muted-foreground">
        requested {constraint.requestedValue} → {realized}
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
  const { blocking = false, unmetCount = 0, grounded = [] } = constraints ?? {};
  return (
    <LedgerSection title="Constraints">
      <LedgerRow label="blocking" value={<BoolBadge value={blocking} />} />
      <LedgerRow
        label="unmet (user-explicit)"
        value={
          <StatusPill
            text={String(unmetCount)}
            tone={unmetCount > 0 ? "warn" : "neutral"}
          />
        }
      />
      {grounded.length === 0 ? (
        <p className="ml-1 pl-2 text-[11px] italic text-muted-foreground">none</p>
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
