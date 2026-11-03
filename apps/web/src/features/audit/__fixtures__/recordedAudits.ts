import { missingGeneAuditSchema } from "@pathfinder/shared/generated/zod/missingGeneAuditSchema";
import { selenoproteinEndAuditSchema } from "@pathfinder/shared/generated/zod/selenoproteinEndAuditSchema";

import recorded from "./recordedAudits.json";

export const SELK_STOPS_AT_SEC = selenoproteinEndAuditSchema.parse(
  recorded.selkStopsAtSec,
);
export const NAC_MISSING_IN_GT1 = missingGeneAuditSchema.parse(
  recorded.nacMissingInGt1,
);
