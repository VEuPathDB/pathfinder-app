import type { GroundedConstraint } from "@pathfinder/shared/generated/types/GroundedConstraint";
import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";

export function groundedEntry(
  label: string,
  status: GroundedConstraint["status"],
  source: "user_explicit" | "assumed" = "user_explicit",
): GroundedConstraint {
  return {
    constraint: {
      kind: "text",
      requestedValue: `${label} value`,
      label,
      source,
      hard: true,
    },
    status,
    realizedValue: null,
    ...(status === "substituted" && { note: `${label} answered another way` }),
  };
}

export const SAMPLE_CAVEAT_SENTENCE =
  "No control genes were attached, so no control test ran.";

export function makeLedger(
  overrides: Partial<InvestigationLedger> = {},
): InvestigationLedger {
  return {
    userIntent: {
      classification: "new_strategy",
      inferredGoal: "Identify transporter genes across Apicomplexa",
      isDifferential: false,
      differentialSides: [],
      explicitConstraints: [],
    },
    frame: {
      present: true,
      diff: null,
      criteriaCount: 2,
      boundCount: 2,
      openSlotCount: 0,
      droppedCount: 0,
      readyToBuild: true,
      needsUser: false,
      contrasts: [],
      structureRender: null,
      spec: null,
    },
    build: {
      pushedCount: 3,
      failedCount: 0,
      skippedCount: 0,
      zeroResultSteps: [],
      needsRecovery: false,
      recoveryKind: "none",
      succeeded: true,
      nodeResults: [],
      wdkStrategyId: null,
    },
    verification: { complete: false, successful: false, caveats: [] },
    constraints: { grounded: [], unmetCount: 0, blocking: false },
    ...overrides,
  };
}
