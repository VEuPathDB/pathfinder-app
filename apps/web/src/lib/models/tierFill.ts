import type { ReasoningEffort } from "@pathfinder/shared";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import {
  isPickableRole,
  PICKABLE_ROLE_DESCRIPTIONS,
  type PickableRole,
} from "./phaseRoles";

export interface RolePicks {
  models: Partial<Record<PickableRole, string>>;
  reasoning: Partial<Record<PickableRole, ReasoningEffort>>;
}

const PICKABLE_ROLES = Object.keys(PICKABLE_ROLE_DESCRIPTIONS).filter(isPickableRole);

// The roles the picker offered after a researcher could save a tier.
const ADDED_ROLES: ReadonlySet<PickableRole> = new Set(["explore"]);

function missingRoles(picks: RolePicks): PickableRole[] {
  return PICKABLE_ROLES.filter((role) => picks.models[role] === undefined);
}

/** Whether the picks are a saved tier that lacks a role the picker added since. */
export function awaitsTierFill(picks: RolePicks): boolean {
  const missing = missingRoles(picks);
  return (
    missing.length > 0 &&
    missing.length < PICKABLE_ROLES.length &&
    missing.every((role) => ADDED_ROLES.has(role))
  );
}

/** A saved tier's picks, with each role the picker added since taken from that tier. */
export function picksFilledFromTier(
  tiers: readonly TierPreset[],
  picks: RolePicks,
): RolePicks {
  if (!awaitsTierFill(picks)) return picks;
  const missing = missingRoles(picks);
  const pinned = PICKABLE_ROLES.filter((role) => picks.models[role] !== undefined);
  const tier = tiers.find((preset) =>
    pinned.every(
      (role) =>
        preset.roles[role]?.modelId === picks.models[role] &&
        preset.roles[role]?.reasoningEffort === picks.reasoning[role],
    ),
  );
  if (tier === undefined) return picks;
  const models = { ...picks.models };
  const reasoning = { ...picks.reasoning };
  for (const role of missing) {
    const config = tier.roles[role];
    if (config === undefined) continue;
    models[role] = config.modelId;
    reasoning[role] = config.reasoningEffort;
  }
  return { models, reasoning };
}
