import type { ReasoningEffort } from "@pathfinder/shared";
import type { PhaseRole } from "@/lib/models/phaseRoles";
import { createPersistedStore } from "./middleware";

export type PhaseModelMap = Partial<Record<PhaseRole, string>>;
export type PhaseReasoningMap = Partial<Record<PhaseRole, ReasoningEffort>>;

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
  setPhaseModel: (role: PhaseRole, id: string | null) => void;
  setPhaseReasoning: (role: PhaseRole, effort: ReasoningEffort | null) => void;
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

function withoutKey<K extends string, V>(
  map: Partial<Record<K, V>>,
  key: K,
): Partial<Record<K, V>> {
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
    // Replace both maps in one commit: a preset is all-or-nothing, and setting
    // phases one at a time would render intermediate half-applied states.
    applyPhasePreset: (models, reasoning) =>
      set({ phaseModels: { ...models }, phaseReasoning: { ...reasoning } }),
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

const PERSISTED_STORE_KEYS = [
  "pathfinder-settings",
  "pathfinder-left-sidebar",
  "pathfinder-right-rail",
] as const;

export function resetAllPersistedSettings(): void {
  if (typeof window === "undefined") return;
  for (const key of PERSISTED_STORE_KEYS) {
    window.localStorage.removeItem(key);
  }
}
