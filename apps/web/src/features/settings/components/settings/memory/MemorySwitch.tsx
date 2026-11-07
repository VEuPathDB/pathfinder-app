"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { MemorySetting } from "@pathfinder/shared";

import { getMemorySetting, putMemorySetting } from "@/features/settings/api/memories";
import { toUserMessage } from "@/lib/api/errors";

import { SettingsSection, SettingsSwitch } from "../SettingsRow";

const MEMORY_SETTING_KEY = ["me", "memory"] as const;

export function MemorySwitch() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: MEMORY_SETTING_KEY,
    queryFn: getMemorySetting,
    meta: { shownInline: true },
  });
  const setEnabled = useMutation({
    mutationFn: async (enabled: boolean) => putMemorySetting({ enabled }),
    onSuccess: (next: MemorySetting) => qc.setQueryData(MEMORY_SETTING_KEY, next),
  });
  return (
    <SettingsSection
      title="Memory"
      description={
        <span data-testid="memory-switch-copy">
          When this is off, PathFinder neither recalls nor saves memories in your
          conversations. The memories below stay until you turn it back on.
        </span>
      }
    >
      {data != null && (
        <SettingsSwitch
          label="Use memory in my conversations"
          checked={data.enabled}
          disabled={setEnabled.isPending}
          onCheckedChange={(next) => setEnabled.mutate(next)}
        />
      )}
      {setEnabled.error != null && (
        <p role="alert" className="text-sm text-destructive">
          Could not save: {toUserMessage(setEnabled.error)}
        </p>
      )}
    </SettingsSection>
  );
}
