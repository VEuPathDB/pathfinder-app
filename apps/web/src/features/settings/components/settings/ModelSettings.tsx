"use client";

import { useQuery } from "@tanstack/react-query";
import type { ModelCatalogEntry, ReasoningEffort } from "@pathfinder/shared";
import { listModelsQueryOptions } from "@pathfinder/shared/generated/hooks/useListModels";
import { listTiersQueryOptions } from "@pathfinder/shared/generated/hooks/useListTiers";
import { useSettingsStore } from "@/state/useSettingsStore";
import { assistantLabel } from "@/lib/assistants";
import { useActiveAssistantId } from "@/features/settings/useActiveAssistantId";
import { phaseDescription, phaseLabel } from "@/lib/models/phaseRoles";
import { ModelPicker } from "@/features/settings/components/ModelPicker";
import { TierPicker } from "@/features/settings/components/TierPicker";
import { ReasoningToggle } from "@/features/settings/components/ReasoningToggle";
import {
  applyTierPreset,
  deriveActiveTier,
  presetsForProvider,
  rolesForAssistant,
} from "@/features/settings/tierPresets";

export function ModelSettings() {
  const { data } = useQuery(listModelsQueryOptions());
  const modelCatalog = data?.models ?? [];
  const phaseDefaults = data?.phaseDefaults ?? {};
  const phaseModels = useSettingsStore((s) => s.phaseModels);
  const setPhaseModel = useSettingsStore((s) => s.setPhaseModel);
  const phaseReasoning = useSettingsStore((s) => s.phaseReasoning);
  const setPhaseReasoning = useSettingsStore((s) => s.setPhaseReasoning);
  const applyPhasePreset = useSettingsStore((s) => s.applyPhasePreset);

  const { data: tierData } = useQuery(listTiersQueryOptions());
  const provider = data?.defaultProvider ?? "";
  const assistantId = useActiveAssistantId();
  const tierPresets = presetsForProvider(tierData?.presets, assistantId, provider);
  const roles = rolesForAssistant(tierData?.presets, assistantId, provider);
  const activeTier = deriveActiveTier(
    tierData?.presets,
    assistantId,
    provider,
    phaseModels,
    phaseReasoning,
    data?.defaultTier,
  );

  return (
    <div className="space-y-1">
      <div className="mb-3">
        <p className="text-xs text-muted-foreground">
          {assistantLabel(assistantId)} runs each stage below on its own model. Pick a
          preset, or set a model + reasoning effort per stage; leave a stage blank to
          use the default.
        </p>
      </div>

      <TierPicker
        presets={tierPresets}
        activeTier={activeTier}
        onSelect={(tier) => {
          const preset = tierPresets[tier];
          if (preset === undefined) return;
          const applied = applyTierPreset(preset);
          applyPhasePreset(applied.models, applied.reasoning);
        }}
      />

      <div className="divide-y divide-border/40">
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
      </div>
    </div>
  );
}

interface PhaseRowProps {
  role: string;
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
  const supportsReasoning = resolvedModel?.supportsReasoning ?? false;
  const effectiveEffort = reasoningEffort ?? "medium";

  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-start gap-3 py-3">
      <div>
        <div className="text-sm font-medium text-foreground">{phaseLabel(role)}</div>
        <div className="text-xs text-muted-foreground">{phaseDescription(role)}</div>
        {defaultModelId !== null && selectedModelId === null && (
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            Default: {defaultModelId}
          </div>
        )}
      </div>
      <ModelPicker
        models={models}
        selectedModelId={selectedModelId}
        onSelect={(id) => onSelectModel(id || null)}
        serverDefaultId={defaultModelId}
      />
      {supportsReasoning ? (
        <ReasoningToggle
          value={effectiveEffort}
          onChange={(effort) => onSelectReasoning(effort)}
        />
      ) : (
        <div className="text-[10px] text-muted-foreground self-center">
          no reasoning
        </div>
      )}
    </div>
  );
}
