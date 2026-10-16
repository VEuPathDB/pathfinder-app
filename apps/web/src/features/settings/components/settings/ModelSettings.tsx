"use client";

import { useQuery } from "@tanstack/react-query";
import type { ModelCatalogEntry, ReasoningEffort } from "@pathfinder/shared";
import { listModelsQueryOptions } from "@pathfinder/shared/generated/hooks/useListModels";
import { listTiersQueryOptions } from "@pathfinder/shared/generated/hooks/useListTiers";
import { useSettingsStore } from "@/state/useSettingsStore";
import { useActiveAssistantId } from "@/features/settings/useActiveAssistantId";
import { useProviderPayers } from "@/lib/hooks/useProviderPayers";
import { withPayers } from "@/lib/models/payers";
import {
  phaseDescription,
  phaseLabel,
  type PickableRole,
} from "@/lib/models/phaseRoles";
import { PROVIDER_TABS } from "@/lib/models/providerMeta";
import { ModelPicker } from "@/features/settings/components/ModelPicker";
import { TierPicker } from "@/features/settings/components/TierPicker";
import { ReasoningSlider } from "@/features/settings/components/ReasoningSlider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import { SettingsRow, SettingsSection } from "./SettingsRow";
import {
  applyTierPreset,
  deriveActiveTier,
  distinctPresets,
  presetOnSwitch,
  presetsForPayer,
  presetsForProvider,
  rolesForAssistant,
} from "@/features/settings/tierPresets";

export function ModelSettings() {
  const { data } = useQuery(listModelsQueryOptions());
  const { payers } = useProviderPayers();
  const modelCatalog = withPayers(data?.models ?? [], payers);
  const phaseDefaults = data?.phaseDefaults ?? {};
  const phaseModels = useSettingsStore((s) => s.phaseModels);
  const setPhaseModel = useSettingsStore((s) => s.setPhaseModel);
  const phaseReasoning = useSettingsStore((s) => s.phaseReasoning);
  const setPhaseReasoning = useSettingsStore((s) => s.setPhaseReasoning);
  const applyPhasePreset = useSettingsStore((s) => s.applyPhasePreset);

  const { data: tierData } = useQuery(listTiersQueryOptions());
  const assistantId = useActiveAssistantId();
  // A provider is offered when someone pays for it and it has presets here.
  const providers = PROVIDER_TABS.filter(
    (tab) =>
      tab.key !== "all" &&
      payers?.[tab.key] !== undefined &&
      Object.keys(presetsForProvider(tierData?.presets, assistantId, tab.key)).length >
        0,
  );
  const leadModelId = phaseModels["lead"] ?? phaseDefaults["lead"];
  const leadProvider = modelCatalog.find((m) => m.id === leadModelId)?.provider;
  const provider = providers.some((tab) => tab.key === leadProvider)
    ? (leadProvider ?? "")
    : (data?.defaultProvider ?? "");
  const presetsFor = (key: string) =>
    presetsForPayer(tierData, payers?.[key] === "user");
  const presets = presetsFor(provider);
  const tierPresets = presetsForProvider(presets, assistantId, provider);
  const roles = rolesForAssistant(presets, assistantId, provider);
  const activeTier = deriveActiveTier(
    presets,
    assistantId,
    provider,
    phaseModels,
    phaseReasoning,
    data?.defaultTier,
  );

  return (
    <div className="space-y-8">
      {providers.length > 1 && (
        <SettingsRow label="Provider">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={provider}
            onValueChange={(next) => {
              const preset = presetOnSwitch(
                presetsForProvider(presetsFor(next), assistantId, next),
                activeTier,
                data?.defaultTier,
              );
              if (preset === undefined) return;
              const applied = applyTierPreset(preset);
              applyPhasePreset(applied.models, applied.reasoning);
            }}
          >
            {providers.map((tab) => (
              <ToggleGroupItem key={tab.key} value={tab.key} className="px-3 text-xs">
                {tab.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </SettingsRow>
      )}

      <TierPicker
        presets={distinctPresets(tierPresets, data?.defaultTier)}
        activeTier={activeTier}
        onSelect={(tier) => {
          const preset = tierPresets[tier];
          if (preset === undefined) return;
          const applied = applyTierPreset(preset);
          applyPhasePreset(applied.models, applied.reasoning);
        }}
      />

      <SettingsSection title="Stages">
        {roles.map((role) => (
          <PhaseRow
            key={role}
            role={role}
            models={modelCatalog}
            defaultModelId={phaseDefaults[role] ?? null}
            selectedModelId={phaseModels[role] ?? null}
            onSelectModel={(id) => setPhaseModel(role, id)}
            reasoningEffort={phaseReasoning[role] ?? null}
            onSelectReasoning={(effort) => setPhaseReasoning(role, effort)}
          />
        ))}
      </SettingsSection>
    </div>
  );
}

interface PhaseRowProps {
  role: PickableRole;
  models: ModelCatalogEntry[];
  defaultModelId: string | null;
  selectedModelId: string | null;
  onSelectModel: (id: string | null) => void;
  reasoningEffort: ReasoningEffort | null;
  onSelectReasoning: (effort: ReasoningEffort | null) => void;
}

function PhaseRow({
  role,
  models,
  defaultModelId,
  selectedModelId,
  onSelectModel,
  reasoningEffort,
  onSelectReasoning,
}: PhaseRowProps) {
  const resolvedModel =
    models.find((m) => m.id === (selectedModelId ?? defaultModelId)) ?? null;
  const defaultModel = models.find((m) => m.id === defaultModelId) ?? null;
  const supportsReasoning = resolvedModel?.supportsReasoning ?? false;
  const effectiveEffort = reasoningEffort ?? "medium";

  return (
    <div
      data-testid={`phase-row-${role}`}
      className="flex items-center justify-between gap-4 py-3"
    >
      <div className="min-w-0">
        <div
          className="text-sm font-medium text-foreground"
          title={phaseDescription(role)}
        >
          {phaseLabel(role)}
        </div>
        {defaultModel !== null && selectedModelId === null && (
          <div className="mt-0.5 truncate text-xs text-muted-foreground">
            Default: {defaultModel.name}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-4">
        <ModelPicker
          models={models}
          selectedModelId={selectedModelId}
          onSelect={(id) => onSelectModel(id || null)}
          serverDefaultId={defaultModelId}
        />
        {supportsReasoning ? (
          <ReasoningSlider
            value={effectiveEffort}
            onChange={(effort) => onSelectReasoning(effort)}
          />
        ) : (
          <span className="w-[11.75rem] text-xs text-muted-foreground">
            No reasoning
          </span>
        )}
      </div>
    </div>
  );
}
