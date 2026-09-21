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
 * Which tier this assistant's picks correspond to, or {@link CUSTOM_TIER}. A
 * tier matches when every one of its roles agrees on model and effort; a role
 * with no pin runs on `deploymentTier`, which is read before the other tiers.
 */
export function deriveActiveTier(
  presets: TierPresetsByAssistant | undefined,
  assistantId: string,
  provider: string,
  models: PhaseModelMap,
  reasoning: PhaseReasoningMap,
  deploymentTier: string | undefined,
): string {
  const candidates = presetsForProvider(presets, assistantId, provider);
  const deployed =
    deploymentTier === undefined ? undefined : candidates[deploymentTier];
  const ordered =
    deploymentTier === undefined || deployed === undefined
      ? Object.entries(candidates)
      : [
          [deploymentTier, deployed] as const,
          ...Object.entries(candidates).filter(([tier]) => tier !== deploymentTier),
        ];
  for (const [tier, preset] of ordered) {
    const matches = Object.entries(preset.roles).every(([role, config]) => {
      const unpinned = deployed?.roles[role];
      return (
        (models[role] ?? unpinned?.modelId) === config.modelId &&
        (reasoning[role] ?? unpinned?.reasoningEffort) === config.reasoningEffort
      );
    });
    if (matches) return tier;
  }
  return CUSTOM_TIER;
}
