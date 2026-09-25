"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Modal } from "@/lib/components/Modal";
import type { SettingsTab } from "../types";
import { DataSettings } from "./settings/DataSettings";
import { AdvancedSettings } from "./settings/AdvancedSettings";
import { SeedingSettings } from "./settings/SeedingSettings";
import { MemorySettings } from "./settings/MemorySettings";
import { ModelSettings } from "./settings/ModelSettings";
import { PrivacySettings } from "./settings/PrivacySettings";
import { ProviderKeySettings } from "./settings/ProviderKeySettings";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "model", label: "Model" },
  { id: "keys", label: "Provider keys" },
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
      <Tabs
        value={tab}
        onValueChange={(next) => {
          const picked = TABS.find((t) => t.id === next);
          if (picked !== undefined) onTabChange(picked.id);
        }}
        className="min-h-0 flex-1 gap-0"
      >
        <TabsList
          variant="line"
          className="h-auto w-full justify-start gap-0 rounded-none border-b border-border p-0 px-5"
        >
          {TABS.map((t) => (
            <TabsTrigger
              key={t.id}
              value={t.id}
              className="h-auto flex-none rounded-none px-4 py-2.5 text-sm font-semibold text-muted-foreground after:bg-primary group-data-[orientation=horizontal]/tabs:after:bottom-0"
            >
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((t) => (
          <TabsContent
            key={t.id}
            value={t.id}
            className="min-h-0 overflow-y-auto px-5 py-4"
          >
            <TabBody tab={t.id} siteId={siteId} />
          </TabsContent>
        ))}
      </Tabs>
    </Modal>
  );
}

function TabBody({ tab, siteId }: { tab: SettingsTab; siteId: string }) {
  switch (tab) {
    case "model":
      return <ModelSettings />;
    case "keys":
      return <ProviderKeySettings />;
    case "data":
      return <DataSettings siteId={siteId} />;
    case "memory":
      return <MemorySettings />;
    case "privacy":
      return <PrivacySettings />;
    case "advanced":
      return <AdvancedSettings />;
    case "seeding":
      return <SeedingSettings />;
  }
}
