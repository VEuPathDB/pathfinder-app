import type { QueryClient } from "@tanstack/react-query";
import { listTiersQueryOptions } from "@pathfinder/shared/generated/hooks/useListTiers";

import { providerOf } from "@/lib/models/payers";
import {
  awaitsTierFill,
  picksFilledFromTier,
  type RolePicks,
} from "@/lib/models/tierFill";
import { useSettingsStore } from "@/state/useSettingsStore";

/** The picks a turn sends; a saved tier gains the roles the picker added since. */
export async function picksForTheTurn(
  queryClient: QueryClient,
  assistantId: string,
): Promise<RolePicks> {
  const { phaseModels, phaseReasoning, applyPhasePreset } = useSettingsStore.getState();
  const picks = { models: phaseModels, reasoning: phaseReasoning };
  const lead = phaseModels.lead;
  if (lead === undefined || !awaitsTierFill(picks)) return picks;
  const tiers = await queryClient.ensureQueryData(listTiersQueryOptions());
  const provider = providerOf(lead);
  const candidates = [tiers.presets, tiers.ownKeyPresets].flatMap((presets) =>
    Object.values(presets[assistantId]?.[provider] ?? {}),
  );
  const filled = picksFilledFromTier(candidates, picks);
  if (filled !== picks) applyPhasePreset(filled.models, filled.reasoning);
  return filled;
}
