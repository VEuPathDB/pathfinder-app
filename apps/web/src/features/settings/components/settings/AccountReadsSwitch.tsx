"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AlwaysAccountReads } from "@pathfinder/shared";

import {
  ALWAYS_ACCOUNT_READS_KEY,
  getAlwaysAllowed,
  setAlwaysAllowed,
} from "@/lib/api/accountReads";
import { toUserMessage } from "@/lib/api/errors";

import { SettingsSection, SettingsSwitch } from "./SettingsRow";

export function AccountReadsSwitch() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ALWAYS_ACCOUNT_READS_KEY,
    queryFn: getAlwaysAllowed,
    meta: { shownInline: true },
  });
  const setAlways = useMutation({
    mutationFn: async (always: boolean) => setAlwaysAllowed(always),
    onSuccess: (next: AlwaysAccountReads) =>
      qc.setQueryData(ALWAYS_ACCOUNT_READS_KEY, next),
  });
  return (
    <SettingsSection
      title="Reading your account"
      description="Strategist asks before it reads your saved strategies, your other conversations or your gene sets. With this on, it reads them without asking."
    >
      {data != null && (
        <SettingsSwitch
          label="Always let Strategist read my account in every conversation"
          checked={data.always}
          disabled={setAlways.isPending}
          onCheckedChange={(next) => setAlways.mutate(next)}
        />
      )}
      {setAlways.error != null && (
        <p role="alert" className="text-sm text-destructive">
          Could not save: {toUserMessage(setAlways.error)}
        </p>
      )}
    </SettingsSection>
  );
}
