import { selenoproteinEndAuditSchema } from "@pathfinder/shared/generated/zod/selenoproteinEndAuditSchema";

import recorded from "./recordedAudits.json";

export const SELK_STOPS_AT_SEC = selenoproteinEndAuditSchema.parse(
  recorded.selkStopsAtSec,
);
