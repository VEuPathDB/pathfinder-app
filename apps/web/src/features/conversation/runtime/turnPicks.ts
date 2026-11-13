import type { QueryClient } from "@tanstack/react-query";
import { listModelsQueryOptions } from "@strategist/shared/generated/hooks/useListModels";
import { listTiersQueryOptions } from "@strategist/shared/generated/hooks/useListTiers";

import { providerOf } from "@/lib/models/payers";
import { isPickableRole } from "@/lib/models/phaseRoles";
import {
  awaitsTierFill,
  picksFilledFromTier,
  type RolePicks,
} from "@/lib/models/tierFill";
import { useSettingsStore } from "@/state/useSettingsStore";

function forgetUnlistedPicks(queryClient: QueryClient): void {
  const catalog = queryClient.getQueryData(listModelsQueryOptions().queryKey);
  if (catalog === undefined) return;
  const listed = new Set(catalog.models.map((model) => model.id));
  const { phaseModels, setPhaseModel, setPhaseReasoning } = useSettingsStore.getState();
  for (const [role, id] of Object.entries(phaseModels)) {
    if (!isPickableRole(role) || listed.has(id)) continue;
    setPhaseModel(role, null);
    setPhaseReasoning(role, null);
  }
}

/** The picks a turn sends; a saved tier gains the roles the picker added since. */
export async function picksForTheTurn(
  queryClient: QueryClient,
  assistantId: string,
): Promise<RolePicks> {
  forgetUnlistedPicks(queryClient);
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
