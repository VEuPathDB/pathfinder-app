"use client";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

import { phaseLabel } from "@/lib/models/phaseRoles";
import { type Tone } from "@/features/conversation/rail/statusTone";

import { BuildDetail, FrameDetail, VerificationDetail } from "./LedgerPanelDetail";
import { LedgerContrasts } from "./LedgerContrasts";
import {
  BoolBadge,
  CountChip,
  LedgerRow,
  LedgerSection,
  StatusPill,
} from "./LedgerPanelPrimitives";

export function IntentSection({
  intent,
}: {
  intent: InvestigationLedger["userIntent"] | undefined;
}) {
  if (intent == null) {
    return (
      <LedgerSection title="Intent">
        <p className="text-xs text-muted-foreground">Not classified yet.</p>
      </LedgerSection>
    );
  }
  const { isDifferential = false, differentialSides = [] } = intent;
  return (
    <LedgerSection title="Intent">
      <LedgerRow
        label="classification"
        value={<StatusPill text={intent.classification} />}
      />
      <LedgerRow label="differential" value={<BoolBadge value={isDifferential} />} />
      <div className="text-xs leading-relaxed">
        <span className="text-muted-foreground">goal: </span>
        <span className="text-foreground">{intent.inferredGoal}</span>
      </div>
      {isDifferential && differentialSides.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">sides:</span>
          {differentialSides.map((side) => (
            <StatusPill key={side} text={side} tone="warn" />
          ))}
        </div>
      )}
    </LedgerSection>
  );
}

export function FrameSection({
  frame,
  detail = false,
}: {
  frame: InvestigationLedger["frame"];
  detail?: boolean;
}) {
  return (
    <LedgerSection title={phaseLabel("frame")}>
      <LedgerRow label="present" value={<BoolBadge value={frame.present} />} />
      <LedgerRow
        label="criteria"
        value={
          <CountChip
            value={frame.criteriaCount}
            tone={frame.criteriaCount > 0 ? "good" : "neutral"}
          />
        }
      />
      <LedgerRow label="bound" value={<CountChip value={frame.boundCount} />} />
      <LedgerRow
        label="open slots"
        value={
          <CountChip
            value={frame.openSlotCount}
            tone={frame.openSlotCount > 0 ? "warn" : "neutral"}
          />
        }
      />
      <LedgerRow
        label="dropped"
        value={
          <CountChip
            value={frame.droppedCount}
            tone={frame.droppedCount > 0 ? "warn" : "neutral"}
          />
        }
      />
      <LedgerRow label="needs user" value={<BoolBadge value={frame.needsUser} />} />
      <LedgerRow
        label="ready to build"
        value={<BoolBadge value={frame.readyToBuild} />}
      />
      <LedgerContrasts contrasts={frame.contrasts} />
      {detail && <FrameDetail frame={frame} />}
    </LedgerSection>
  );
}

export function BuildSection({
  build,
  detail = false,
}: {
  build: InvestigationLedger["build"];
  detail?: boolean;
}) {
  const {
    pushedCount = 0,
    failedCount = 0,
    skippedCount = 0,
    zeroResultSteps = [],
    needsRecovery = false,
    recoveryKind = "none",
  } = build;
  const recoveryTone: Tone =
    recoveryKind === "none"
      ? "neutral"
      : recoveryKind === "transient_retry"
        ? "warn"
        : "bad";
  return (
    <LedgerSection title="Build">
      <LedgerRow
        label="pushed"
        value={
          <CountChip value={pushedCount} tone={pushedCount > 0 ? "good" : "neutral"} />
        }
      />
      <LedgerRow
        label="failed"
        value={
          <CountChip value={failedCount} tone={failedCount > 0 ? "bad" : "neutral"} />
        }
      />
      <LedgerRow
        label="skipped"
        value={
          <CountChip
            value={skippedCount}
            tone={skippedCount > 0 ? "warn" : "neutral"}
          />
        }
      />
      <LedgerRow
        label="zero-result steps"
        value={
          <CountChip
            value={zeroResultSteps.length}
            tone={zeroResultSteps.length > 0 ? "warn" : "neutral"}
          />
        }
      />
      <LedgerRow label="needs recovery" value={<BoolBadge value={needsRecovery} />} />
      <LedgerRow
        label="recovery kind"
        value={<StatusPill text={recoveryKind} tone={recoveryTone} />}
      />
      <LedgerRow label="succeeded" value={<BoolBadge value={build.succeeded} />} />
      {detail && <BuildDetail build={build} />}
    </LedgerSection>
  );
}

export function VerificationSection({
  verification,
  detail = false,
}: {
  verification: InvestigationLedger["verification"];
  detail?: boolean;
}) {
  return (
    <LedgerSection title="Verification">
      <LedgerRow label="complete" value={<BoolBadge value={verification.complete} />} />
      <LedgerRow
        label="successful"
        value={<BoolBadge value={verification.successful} />}
      />
      {detail && <VerificationDetail verification={verification} />}
    </LedgerSection>
  );
}
