import type { ReasoningEffort } from "@pathfinder/shared";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";

/** Not a server tier: the label shown when the per-role picks match no preset. */
export const CUSTOM_TIER = "custom";

/** The wire shape of GET /api/v1/tiers: assistant -> provider -> tier. */
export type TierPresetsByAssistant = Record<
  string,
  Record<string, Record<string, TierPreset>>
>;

export type PhaseModelMap = Record<string, string>;
export type PhaseReasoningMap = Record<string, ReasoningEffort>;

export interface AppliedTier {
  models: PhaseModelMap;
  reasoning: PhaseReasoningMap;
}

/** The tiers offered for one assistant on one provider; empty while presets
 *  load, or when neither is configured. */
export function presetsForProvider(
  presets: TierPresetsByAssistant | undefined,
  assistantId: string,
  provider: string,
): Record<string, TierPreset> {
  return presets?.[assistantId]?.[provider] ?? {};
}

/** The roles the assistant in use runs, in the order its presets name them. */
export function rolesForAssistant(
  presets: TierPresetsByAssistant | undefined,
  assistantId: string,
  provider: string,
): string[] {
  const tiers = Object.values(presetsForProvider(presets, assistantId, provider));
  const first = tiers[0];
  return first === undefined ? [] : Object.keys(first.roles);
}

/** Expand a preset into the per-role picks the settings store holds. */
export function applyTierPreset(preset: TierPreset): AppliedTier {
  const models: PhaseModelMap = {};
  const reasoning: PhaseReasoningMap = {};
  for (const [role, config] of Object.entries(preset.roles)) {
    models[role] = config.modelId;
    reasoning[role] = config.reasoningEffort;
  }
  return { models, reasoning };
}

/**
 * Which tier the current picks correspond to, or {@link CUSTOM_TIER}.
 *
 * Derived rather than stored, so the label can never drift from the pickers it
 * describes. A tier matches only when EVERY role of that preset agrees on both
 * model and effort -- some tiers differ from each other by effort alone, so
 * comparing models only would conflate them. A role of another assistant is
 * never read, so one assistant's picks do not decide another's label.
 */
export function deriveActiveTier(
  presets: TierPresetsByAssistant | undefined,
  assistantId: string,
  provider: string,
  models: PhaseModelMap,
  reasoning: PhaseReasoningMap,
): string {
  const candidates = presetsForProvider(presets, assistantId, provider);
  for (const [tier, preset] of Object.entries(candidates)) {
    const matches = Object.entries(preset.roles).every(
      ([role, config]) =>
        models[role] === config.modelId && reasoning[role] === config.reasoningEffort,
    );
    if (matches) return tier;
  }
  return CUSTOM_TIER;
}
