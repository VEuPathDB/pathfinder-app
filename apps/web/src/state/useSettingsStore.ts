import type { ReasoningEffort } from "@pathfinder/shared";
import { createPersistedStore } from "./middleware";
import { useLeftSidebarStore, useRightRailStore } from "./useRightRailStore";

// Roles are data the tier presets name, so the picks are keyed by plain role
// names rather than by a role set this store declares.
export type PhaseModelMap = Record<string, string>;
export type PhaseReasoningMap = Record<string, ReasoningEffort>;

interface SettingsState {
  showRawToolCalls: boolean;
  showTokenUsage: boolean;
  deleteFromWdk: boolean;
  firstRunHintDismissed: boolean;
  phaseModels: PhaseModelMap;
  phaseReasoning: PhaseReasoningMap;

  setShowRawToolCalls: (show: boolean) => void;
  setShowTokenUsage: (show: boolean) => void;
  setDeleteFromWdk: (v: boolean) => void;
  dismissFirstRunHint: () => void;
  setPhaseModel: (role: string, id: string | null) => void;
  setPhaseReasoning: (role: string, effort: ReasoningEffort | null) => void;
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
};

function withoutKey<V>(map: Record<string, V>, key: string): Record<string, V> {
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
    name: "pathfinder-settings",
    partialize: (s) => ({
      showRawToolCalls: s.showRawToolCalls,
      showTokenUsage: s.showTokenUsage,
      deleteFromWdk: s.deleteFromWdk,
      firstRunHintDismissed: s.firstRunHintDismissed,
      phaseModels: s.phaseModels,
      phaseReasoning: s.phaseReasoning,
    }),
  },
);

/** Clear the stored settings, sidebar and right rail under the keys they persist to. */
export function resetAllPersistedSettings(): void {
  for (const store of [useSettingsStore, useLeftSidebarStore, useRightRailStore]) {
    store.persist.clearStorage();
  }
}
