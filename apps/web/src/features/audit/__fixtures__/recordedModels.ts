import { findingModelsSchema } from "@pathfinder/shared/generated/zod/findingModelsSchema";

import recorded from "./recordedModels.json";

export const PKAC_MODELS = findingModelsSchema.parse(recorded.pkac);
export const AFU8_MODELS = findingModelsSchema.parse(recorded.afu8);
export const AGAP3685_MODELS = findingModelsSchema.parse(recorded.agap3685);
export const AGAP3685_RETAINED_MODELS = findingModelsSchema.parse(
  recorded.agap3685Retained,
);
export const AGAP3685_NONCANONICAL_MODELS = findingModelsSchema.parse(
  recorded.agap3685Noncanonical,
);
export const AGAP7279_MODELS = findingModelsSchema.parse(recorded.agap7279);
export const RPT6_MODELS = findingModelsSchema.parse(recorded.rpt6);
export const GT1_SELK_MODELS = findingModelsSchema.parse(recorded.gt1Selk);
