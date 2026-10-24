import { createStore } from "./middleware";

export type SettingsTab = "model" | "keys" | "data" | "memory" | "privacy" | "advanced";

interface SettingsModalState {
  isOpen: boolean;
  tab: SettingsTab;
  open: (tab?: SettingsTab) => void;
  close: () => void;
  setTab: (tab: SettingsTab) => void;
}

export const useSettingsModalStore = createStore<SettingsModalState>(
  "SettingsModalStore",
  (set) => ({
    isOpen: false,
    tab: "model",
    open: (tab) => set((s) => ({ isOpen: true, tab: tab ?? s.tab })),
    close: () => set({ isOpen: false }),
    setTab: (tab) => set({ tab }),
  }),
);
