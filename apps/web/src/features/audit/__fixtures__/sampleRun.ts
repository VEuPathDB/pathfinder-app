import { auditRunViewSchema } from "@pathfinder/shared/generated/zod/auditRunViewSchema";
import { findingDetailSchema } from "@pathfinder/shared/generated/zod/findingDetailSchema";
import { findingPageSchema } from "@pathfinder/shared/generated/zod/findingPageSchema";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { FindingViewCheckEnumKey } from "@pathfinder/shared/generated/types/FindingView";

import recorded from "./sampleRun.json";

export const SAMPLE_RUN_ID = "00000000-0000-4000-8000-000000000001";
export const SAMPLE_RUN = auditRunViewSchema.parse(recorded.run);
export const SAMPLE_FINDINGS = findingPageSchema.parse(recorded.findings);
export const SAMPLE_DETAILS: FindingDetail[] = recorded.details.map((detail) =>
  findingDetailSchema.parse(detail),
);

export function sampleDetail(check: FindingViewCheckEnumKey): FindingDetail {
  return errorDetail(SAMPLE_DETAILS, check);
}

export function errorDetail(
  details: readonly FindingDetail[],
  check: FindingViewCheckEnumKey,
): FindingDetail {
  const found = details.find(
    (detail) => detail.finding.check === check && detail.finding.errorType !== null,
  );
  if (found === undefined) throw new Error(`the sample run holds no ${check} error`);
  return found;
}
