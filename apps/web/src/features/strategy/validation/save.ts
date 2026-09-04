import type { Step, Strategy } from "@pathfinder/shared";
import { validateSearchParams } from "@/lib/api/sites";
import { toUserMessage } from "@/lib/api/errors";
import { formatSearchValidationResponse } from "./format";
import { validateStrategySteps } from "@/features/strategy/graph";
import { normalizeRecordType } from "@/lib/utils/normalizeRecordType";
import { inferStepKind } from "@/features/strategy/graph";

export async function validateStepsForSave(args: {
  siteId: string;
  steps: Step[];
  strategy: Strategy | null;
}): Promise<{
  errorsByStepId: Record<string, string | undefined>;
  hasErrors: boolean;
}> {
  const { siteId, steps, strategy } = args;
  const errorsByStepId: Record<string, string | undefined> = {};

  if (steps.length === 0) return { errorsByStepId, hasErrors: false };

  const structuralErrors = validateStrategySteps(steps).filter(
    (e) => e.severity === "error",
  );
  for (const issue of structuralErrors) {
    if (issue.stepId != null && issue.stepId !== "") {
      errorsByStepId[issue.stepId] = `Cannot be saved: ${issue.message}`;
    }
  }

  await Promise.all(
    steps.map(async (step) => {
      if (inferStepKind(step) !== "search") {
        // Preserve structural errors already set (MISSING_INPUT, MISSING_OPERATOR, etc.).
        // Only clear when there is no structural issue.
        return;
      }

      const rawRecordType = step.recordType ?? strategy?.recordType ?? null;
      const recordType = normalizeRecordType(rawRecordType);
      const searchName = step.searchName;

      if (
        recordType == null ||
        recordType === "" ||
        searchName == null ||
        searchName === ""
      ) {
        errorsByStepId[step.id] =
          "Cannot be saved: search name or record type missing.";
        return;
      }

      try {
        const response = await validateSearchParams(
          siteId,
          recordType,
          searchName,
          step.parameters ?? {},
        );
        const formatted = formatSearchValidationResponse(response);
        errorsByStepId[step.id] ??= formatted.message ?? undefined;
      } catch (err) {
        errorsByStepId[step.id] ??=
          `Cannot be saved: ${toUserMessage(err, "validation failed.")}`;
      }
    }),
  );

  const hasErrors = Object.values(errorsByStepId).some(Boolean);
  return { errorsByStepId, hasErrors };
}
