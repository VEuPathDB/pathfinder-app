import { useState } from "react";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";
import { type SettingsTab, useSettingsModalStore } from "@/state/useSettingsModalStore";

interface ModalState {
  showSettings: boolean;
  settingsTab: SettingsTab;
  openSettings: (tab?: SettingsTab) => void;
  setSettingsTab: (tab: SettingsTab) => void;
  closeSettings: () => void;

  graphEditing: boolean;
  openGraphEditor: () => void;
  closeGraphEditor: () => void;
}

export function useModalState(): ModalState {
  const showSettings = useSettingsModalStore((s) => s.isOpen);
  const settingsTab = useSettingsModalStore((s) => s.tab);
  const openSettings = useSettingsModalStore((s) => s.open);
  const close = useSettingsModalStore((s) => s.close);
  const setTab = useSettingsModalStore((s) => s.setTab);
  const [graphEditing, setGraphEditing] = useState(false);
  // A memory the thread focuses holds the modal open on the memory tab.
  const memoryFocused = useMemoryFocusStore((s) => s.focused !== null);
  const clearFocus = useMemoryFocusStore((s) => s.clearFocus);

  const changeSettingsTab = (tab: SettingsTab) => {
    if (memoryFocused) openSettings();
    clearFocus();
    setTab(tab);
  };
  const closeSettings = () => {
    clearFocus();
    close();
  };
  const openGraphEditor = () => setGraphEditing(true);
  const closeGraphEditor = () => setGraphEditing(false);

  return {
    showSettings: showSettings || memoryFocused,
    settingsTab: memoryFocused ? "memory" : settingsTab,
    openSettings,
    setSettingsTab: changeSettingsTab,
    closeSettings,
    graphEditing,
    openGraphEditor,
    closeGraphEditor,
  };
}
