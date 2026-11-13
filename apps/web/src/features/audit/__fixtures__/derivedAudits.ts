import { missingGeneAuditSchema } from "@strategist/shared/generated/zod/missingGeneAuditSchema";
import { relativesEvidenceSchema } from "@strategist/shared/generated/zod/relativesEvidenceSchema";

import derived from "./derivedAudits.json";

export const NAC_MISSING_IN_GT1 = missingGeneAuditSchema.parse(derived.nacMissingInGt1);
export const RELATIVES_ONE_IN_EACH_TIER = relativesEvidenceSchema.parse(
  derived.relativesOneInEachTier,
);
export const RELATIVES_REFERENCE_NO_LENGTH = relativesEvidenceSchema.parse(
  derived.relativesReferenceNoLength,
);
export const RELATIVES_OWN_SPECIES_ONLY = relativesEvidenceSchema.parse(
  derived.relativesOwnSpeciesOnly,
);
export const RELATIVES_NO_REFERENCE_ROW = relativesEvidenceSchema.parse(
  derived.relativesNoReferenceRow,
);
