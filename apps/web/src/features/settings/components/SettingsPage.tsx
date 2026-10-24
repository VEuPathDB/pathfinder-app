"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Modal } from "@/lib/components/Modal";
import type { SettingsTab } from "@/state/useSettingsModalStore";
import { DataSettings } from "./settings/DataSettings";
import { AdvancedSettings } from "./settings/AdvancedSettings";
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
        orientation="vertical"
        value={tab}
        onValueChange={(next) => {
          const picked = TABS.find((t) => t.id === next);
          if (picked !== undefined) onTabChange(picked.id);
        }}
        className="h-[min(85vh,36rem)] min-h-0 gap-0"
      >
        <div className="flex w-32 shrink-0 flex-col gap-3 border-r border-border bg-muted/30 p-3 sm:w-44">
          <p className="px-2 pt-1 text-sm font-semibold text-foreground">Settings</p>
          <TabsList variant="line" className="w-full items-stretch gap-0.5 p-0">
            {TABS.map((t) => (
              <TabsTrigger
                key={t.id}
                value={t.id}
                className="h-8 flex-none rounded-md px-2 text-[13px] font-medium text-muted-foreground after:hidden hover:bg-muted/60 group-data-[variant=line]/tabs-list:data-[state=active]:bg-muted data-[state=active]:text-foreground"
              >
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {TABS.map((t) => (
          <TabsContent
            key={t.id}
            value={t.id}
            className="min-h-0 min-w-0 overflow-y-auto px-6 pt-12 pb-6"
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
  }
}
