import type { ModelCatalogEntry } from "@pathfinder/shared";
import type { PaidBy } from "@pathfinder/shared/generated/types/PaidBy";

/**
 * Who pays for each provider, as `GET /api/v1/me/provider-keys` reports it.
 * The server's payer rule decides; this mirrors it for display.
 */
export type Payers = Readonly<Record<string, PaidBy>>;

type RoleModels = Readonly<Record<string, string>>;

interface PresetsWithRoles {
  readonly roles: Readonly<Record<string, unknown>>;
}

type PresetsByAssistant = Readonly<
  Record<string, Readonly<Record<string, Readonly<Record<string, PresetsWithRoles>>>>>
>;

function providerOf(modelId: string): string {
  return modelId.split(":")[0] ?? "";
}

/**
 * A model can be picked when someone pays for its provider. Without the
 * reader's payers the deployment's own view decides.
 */
export function selectable(
  entry: ModelCatalogEntry,
  payers: Payers | undefined,
): boolean {
  if (payers === undefined) return entry.enabled ?? true;
  return payers[entry.provider] !== undefined;
}

/** Whether the model runs on the researcher's own key. */
export function onOwnKey(
  entry: ModelCatalogEntry,
  payers: Payers | undefined,
): boolean {
  return payers?.[entry.provider] === "user";
}

/** The catalog with `enabled` read from the payers. */
export function withPayers(
  models: readonly ModelCatalogEntry[],
  payers: Payers | undefined,
): ModelCatalogEntry[] {
  return models.map((model) => ({ ...model, enabled: selectable(model, payers) }));
}

function modelsOf(roles: readonly string[], picks: RoleModels, defaults: RoleModels) {
  return roles.map((role) => ({ role, model: picks[role] ?? defaults[role] }));
}

/**
 * The roles the deployment pays for this turn. A role whose provider has no
 * known payer counts as the deployment's; the server refuses it either way.
 */
export function rolesPaidByDeployment(
  roles: readonly string[],
  picks: RoleModels,
  defaults: RoleModels,
  payers: Payers | undefined,
): string[] {
  return modelsOf(roles, picks, defaults)
    .filter(
      ({ model }) => model === undefined || payers?.[providerOf(model)] !== "user",
    )
    .map(({ role }) => role);
}

/** The refused providers some role of this turn runs on. */
export function refusedProvidersInUse(
  roles: readonly string[],
  picks: RoleModels,
  defaults: RoleModels,
  refused: readonly string[],
): string[] {
  const inUse = new Set(
    modelsOf(roles, picks, defaults).flatMap(({ model }) =>
      model === undefined ? [] : [providerOf(model)],
    ),
  );
  return refused.filter((provider) => inUse.has(provider));
}

/** The roles an assistant runs, as its tier presets name them. */
export function assistantRoles(
  presets: PresetsByAssistant | undefined,
  assistantId: string,
): string[] {
  const byProvider = presets?.[assistantId] ?? {};
  const roles = Object.values(byProvider).flatMap((tiers) =>
    Object.values(tiers).flatMap((preset) => Object.keys(preset.roles)),
  );
  return [...new Set(roles)];
}
