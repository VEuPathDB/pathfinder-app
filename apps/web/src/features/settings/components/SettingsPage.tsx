"use client";

import { Modal } from "@/lib/components/Modal";
import type { SettingsTab } from "../types";
import { DataSettings } from "./settings/DataSettings";
import { AdvancedSettings } from "./settings/AdvancedSettings";
import { SeedingSettings } from "./settings/SeedingSettings";
import { MemorySettings } from "./settings/MemorySettings";
import { ModelSettings } from "./settings/ModelSettings";
import { PrivacySettings } from "./settings/PrivacySettings";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "model", label: "Model" },
  { id: "data", label: "Data" },
  { id: "memory", label: "Memory" },
  { id: "privacy", label: "Privacy" },
  { id: "advanced", label: "Advanced" },
  { id: "seeding", label: "Seeding" },
];

interface SettingsPageProps {
  open: boolean;
  onClose: () => void;
  siteId: string;
  tab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
}

export function SettingsPage({
  open,
  onClose,
  siteId,
  tab,
  onTabChange,
}: SettingsPageProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Settings"
      maxWidth="max-w-3xl"
      showCloseButton
    >
      {/* Tabs */}
      <div className="flex border-b border-border px-5">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onTabChange(t.id)}
            className={`px-4 py-2.5 text-sm font-semibold transition-colors ${
              tab === t.id
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content - scrollable */}
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {tab === "model" && <ModelSettings />}
        {tab === "data" && <DataSettings siteId={siteId} />}
        {tab === "memory" && <MemorySettings />}
        {tab === "privacy" && <PrivacySettings />}
        {tab === "advanced" && <AdvancedSettings />}
        {tab === "seeding" && <SeedingSettings />}
      </div>
    </Modal>
  );
}
