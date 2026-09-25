import { useState } from "react";
import type { SettingsTab } from "@/features/settings/types";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";

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
  const [showSettings, setShowSettings] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("model");
  const [graphEditing, setGraphEditing] = useState(false);
  // A memory the thread focuses holds the modal open on the memory tab.
  const memoryFocused = useMemoryFocusStore((s) => s.focused !== null);
  const clearFocus = useMemoryFocusStore((s) => s.clearFocus);

  const openSettings = (tab?: SettingsTab) => {
    if (tab !== undefined) setSettingsTab(tab);
    setShowSettings(true);
  };
  const changeSettingsTab = (tab: SettingsTab) => {
    if (memoryFocused) setShowSettings(true);
    clearFocus();
    setSettingsTab(tab);
  };
  const closeSettings = () => {
    clearFocus();
    setShowSettings(false);
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
