import { findingModelsSchema } from "@pathfinder/shared/generated/zod/findingModelsSchema";

import derived from "./derivedModels.json";

export const AGAP3685_RETAINED_MODELS = findingModelsSchema.parse(
  derived.agap3685Retained,
);
export const AGAP3685_NONCANONICAL_MODELS = findingModelsSchema.parse(
  derived.agap3685Noncanonical,
);
export const GT1_SELK_NOT_AT_SEC_MODELS = findingModelsSchema.parse(
  derived.gt1SelkNotAtSec,
);
export const SEC_MINUS_STRAND_MODELS = findingModelsSchema.parse(
  derived.secMinusStrand,
);
export const SEC_SPLIT_STOP_MODELS = findingModelsSchema.parse(derived.secSplitStop);
