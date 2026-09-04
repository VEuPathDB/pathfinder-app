import type { ReasoningEffort } from "@pathfinder/shared";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { PHASE_ROLES, type PhaseRole } from "@/lib/models/phaseRoles";

/** Not a server tier: the label shown when the per-phase picks match no preset. */
export const CUSTOM_TIER = "custom";

export type TierPresetsByProvider = Record<string, Record<string, TierPreset>>;

export type PhaseModelMap = Partial<Record<PhaseRole, string>>;
export type PhaseReasoningMap = Partial<Record<PhaseRole, ReasoningEffort>>;

export interface AppliedTier {
  models: PhaseModelMap;
  reasoning: PhaseReasoningMap;
}

/** The tiers offered for one provider; empty while presets load or if unknown. */
export function presetsForProvider(
  presets: TierPresetsByProvider | undefined,
  provider: string,
): Record<string, TierPreset> {
  return presets?.[provider] ?? {};
}

/** Expand a preset into the per-phase picks the settings store holds. */
export function applyTierPreset(preset: TierPreset): AppliedTier {
  const models: PhaseModelMap = {};
  const reasoning: PhaseReasoningMap = {};
  for (const role of PHASE_ROLES) {
    models[role] = preset[role].modelId;
    reasoning[role] = preset[role].reasoningEffort;
  }
  return { models, reasoning };
}

/**
 * Which tier the current per-phase picks correspond to, or {@link CUSTOM_TIER}.
 *
 * Derived rather than stored, so the label can never drift from the pickers it
 * describes. A tier matches only when EVERY phase agrees on both model and
 * effort -- some tiers differ from each other by effort alone, so comparing
 * models only would conflate them.
 */
export function deriveActiveTier(
  presets: TierPresetsByProvider | undefined,
  provider: string,
  models: PhaseModelMap,
  reasoning: PhaseReasoningMap,
): string {
  const candidates = presetsForProvider(presets, provider);
  for (const [tier, preset] of Object.entries(candidates)) {
    const matches = PHASE_ROLES.every(
      (role) =>
        models[role] === preset[role].modelId &&
        reasoning[role] === preset[role].reasoningEffort,
    );
    if (matches) return tier;
  }
  return CUSTOM_TIER;
}
