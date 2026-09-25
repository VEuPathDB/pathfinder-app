"use client";

import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

import { phaseLabel } from "@/lib/models/phaseRoles";
import { type Tone } from "@/features/conversation/rail/statusTone";

import {
  BuildDetail,
  type CheckedEvidence,
  FrameDetail,
  VerificationDetail,
} from "./LedgerPanelDetail";
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
        label="searches"
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
      <LedgerRow
        label="needs your answer"
        value={<BoolBadge value={frame.needsUser} />}
      />
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
    <LedgerSection title={phaseLabel("execution")}>
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

/** One control set as the summary reads it: returned of controls. */
function controlCounts(evidence: CheckedEvidence): string {
  return evidence.card.controls
    .flatMap((test) => [
      ...(test.positive == null
        ? []
        : [`${test.positive.returnedCount}/${test.positive.controlsCount} positives`]),
      ...(test.negative == null
        ? []
        : [`${test.negative.returnedCount}/${test.negative.controlsCount} negatives`]),
    ])
    .join(", ");
}

export function VerificationSection({
  verification,
  evidence = null,
  detail = false,
}: {
  verification: InvestigationLedger["verification"];
  evidence?: CheckedEvidence | null;
  detail?: boolean;
}) {
  const digest = verification.digest;
  const pending = digest?.success === true ? (digest.pendingChecks ?? []) : [];
  return (
    <LedgerSection title={phaseLabel("verification")}>
      <LedgerRow label="complete" value={<BoolBadge value={verification.complete} />} />
      <LedgerRow
        label="successful"
        value={
          pending.length > 0 ? (
            <StatusPill text={`${pending.length} pending`} tone="warn" />
          ) : (
            <BoolBadge value={verification.successful} />
          )
        }
      />
      {evidence !== null && evidence.card.controls.length > 0 && (
        <LedgerRow label="controls returned" value={controlCounts(evidence)} />
      )}
      {detail && <VerificationDetail verification={verification} evidence={evidence} />}
    </LedgerSection>
  );
}
