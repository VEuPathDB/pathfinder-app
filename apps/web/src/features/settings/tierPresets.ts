import type { PhaseTierConfig } from "@pathfinder/shared/generated/types/PhaseTierConfig";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { isPickableRole, type PickableRole } from "@/lib/models/phaseRoles";
import type { PhaseModelMap, PhaseReasoningMap } from "@/state/useSettingsStore";

/** Not a server tier: the label shown when the per-role picks match no preset. */
export const CUSTOM_TIER = "custom";

/** The wire shape of GET /api/v1/tiers: assistant -> provider -> tier. */
export type TierPresetsByAssistant = Record<
  string,
  Record<string, Record<string, TierPreset>>
>;

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

/** The roles of a preset the researcher picks a model for, with their configs. */
function pickableConfigs(preset: TierPreset): [PickableRole, PhaseTierConfig][] {
  return Object.entries(preset.roles).flatMap(
    ([role, config]): [PickableRole, PhaseTierConfig][] =>
      isPickableRole(role) ? [[role, config]] : [],
  );
}

/** The roles of the assistant in use the researcher picks a model for, in the
 *  order its presets name them. */
export function rolesForAssistant(
  presets: TierPresetsByAssistant | undefined,
  assistantId: string,
  provider: string,
): PickableRole[] {
  const tiers = Object.values(presetsForProvider(presets, assistantId, provider));
  const first = tiers[0];
  return first === undefined ? [] : pickableConfigs(first).map(([role]) => role);
}

/** Expand a preset into the per-role picks the settings store holds. */
export function applyTierPreset(preset: TierPreset): AppliedTier {
  const models: PhaseModelMap = {};
  const reasoning: PhaseReasoningMap = {};
  for (const [role, config] of pickableConfigs(preset)) {
    models[role] = config.modelId;
    reasoning[role] = config.reasoningEffort;
  }
  return { models, reasoning };
}

/**
 * Which tier this assistant's picks correspond to, or {@link CUSTOM_TIER}. A
 * tier matches when every role the researcher picks agrees on model and effort;
 * a role with no pin runs on `deploymentTier`, which is read before the others.
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
    const matches = pickableConfigs(preset).every(([role, config]) => {
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
