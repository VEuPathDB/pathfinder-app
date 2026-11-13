import type { ReasoningEffort } from "@strategist/shared";
import { reasoningEffortSchema } from "@strategist/shared/generated/zod/reasoningEffortSchema";
import { z } from "zod";
import { pickableOnly, type PickableRole } from "@/lib/models/phaseRoles";
import {
  applyTextScale,
  DEFAULT_TEXT_SCALE,
  TEXT_SCALES,
  type TextScale,
} from "@/lib/textScale";
import { createPersistedStore } from "./middleware";
import { useLeftSidebarStore, useRightRailStore } from "./useRightRailStore";

export type PhaseModelMap = Partial<Record<PickableRole, string>>;
export type PhaseReasoningMap = Partial<Record<PickableRole, ReasoningEffort>>;

interface SettingsState {
  showRawToolCalls: boolean;
  showTokenUsage: boolean;
  deleteFromWdk: boolean;
  firstRunHintDismissed: boolean;
  phaseModels: PhaseModelMap;
  phaseReasoning: PhaseReasoningMap;
  textScale: TextScale;

  setShowRawToolCalls: (show: boolean) => void;
  setShowTokenUsage: (show: boolean) => void;
  setDeleteFromWdk: (v: boolean) => void;
  setTextScale: (scale: TextScale) => void;
  dismissFirstRunHint: () => void;
  setPhaseModel: (role: PickableRole, id: string | null) => void;
  setPhaseReasoning: (role: PickableRole, effort: ReasoningEffort | null) => void;
  applyPhasePreset: (models: PhaseModelMap, reasoning: PhaseReasoningMap) => void;
  resetToDefaults: () => void;
}

const DEFAULTS = {
  showRawToolCalls: false,
  showTokenUsage: true,
  deleteFromWdk: false,
  firstRunHintDismissed: false,
  phaseModels: {} as PhaseModelMap,
  phaseReasoning: {} as PhaseReasoningMap,
  textScale: DEFAULT_TEXT_SCALE,
};

// The fields a browser keeps. A stored pick for a role the researcher cannot
// pick is dropped when the fields are read back.
const storedSettings = z.object({
  showRawToolCalls: z.boolean().default(DEFAULTS.showRawToolCalls),
  showTokenUsage: z.boolean().default(DEFAULTS.showTokenUsage),
  deleteFromWdk: z.boolean().default(DEFAULTS.deleteFromWdk),
  firstRunHintDismissed: z.boolean().default(DEFAULTS.firstRunHintDismissed),
  phaseModels: z.record(z.string(), z.string()).transform(pickableOnly).default({}),
  phaseReasoning: z
    .record(z.string(), reasoningEffortSchema)
    .transform(pickableOnly)
    .default({}),
  textScale: z
    .union(TEXT_SCALES.map((scale) => z.literal(scale)))
    .catch(DEFAULTS.textScale),
});

function withoutKey<V>(
  map: Partial<Record<PickableRole, V>>,
  key: PickableRole,
): Partial<Record<PickableRole, V>> {
  const next = { ...map };
  delete next[key];
  return next;
}

export const useSettingsStore = createPersistedStore<SettingsState>(
  "SettingsStore",
  (set) => ({
    ...DEFAULTS,

    setShowRawToolCalls: (show) => set({ showRawToolCalls: show }),
    setShowTokenUsage: (show) => set({ showTokenUsage: show }),
    setDeleteFromWdk: (v) => set({ deleteFromWdk: v }),
    setTextScale: (scale) => set({ textScale: scale }),
    dismissFirstRunHint: () => set({ firstRunHintDismissed: true }),
    setPhaseModel: (role, id) =>
      set((state) => ({
        phaseModels:
          id == null || id === ""
            ? withoutKey(state.phaseModels, role)
            : { ...state.phaseModels, [role]: id },
      })),
    setPhaseReasoning: (role, effort) =>
      set((state) => ({
        phaseReasoning:
          effort == null
            ? withoutKey(state.phaseReasoning, role)
            : { ...state.phaseReasoning, [role]: effort },
      })),
    // Both maps move in one commit: a preset is all-or-nothing, and setting
    // roles one at a time would render intermediate half-applied states. A
    // preset covers one assistant, so the roles of the others are kept.
    applyPhasePreset: (models, reasoning) =>
      set((state) => ({
        phaseModels: { ...state.phaseModels, ...models },
        phaseReasoning: { ...state.phaseReasoning, ...reasoning },
      })),
    resetToDefaults: () => set({ ...DEFAULTS, phaseModels: {}, phaseReasoning: {} }),
  }),
  {
    name: "strategist-settings",
    partialize: (s) => storedSettings.parse(s),
    merge: (stored, current) => ({
      ...current,
      ...storedSettings.optional().parse(stored),
    }),
  },
);

if (typeof document !== "undefined") {
  useSettingsStore.subscribe((s) => s.textScale, applyTextScale, {
    fireImmediately: true,
  });
}

export function usesDefaultModels(
  state: Pick<SettingsState, "phaseModels" | "phaseReasoning">,
): boolean {
  return (
    Object.keys(state.phaseModels).length === 0 &&
    Object.keys(state.phaseReasoning).length === 0
  );
}

/** Clear the stored settings, sidebar and right rail under the keys they persist to. */
export function resetAllPersistedSettings(): void {
  for (const store of [useSettingsStore, useLeftSidebarStore, useRightRailStore]) {
    store.persist.clearStorage();
  }
}
