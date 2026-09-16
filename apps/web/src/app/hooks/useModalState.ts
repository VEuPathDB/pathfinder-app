import { useState } from "react";
import type { SettingsTab } from "@/features/settings/types";

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

  const openSettings = (tab?: SettingsTab) => {
    if (tab !== undefined) setSettingsTab(tab);
    setShowSettings(true);
  };
  const closeSettings = () => setShowSettings(false);
  const openGraphEditor = () => setGraphEditing(true);
  const closeGraphEditor = () => setGraphEditing(false);

  return {
    showSettings,
    settingsTab,
    openSettings,
    setSettingsTab,
    closeSettings,
    graphEditing,
    openGraphEditor,
    closeGraphEditor,
  };
}
