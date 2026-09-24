"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import type { PrivacySettings as PrivacySettingsValue } from "@pathfinder/shared";

import {
  getPrivacySettings,
  updatePrivacySettings,
} from "@/features/settings/api/privacy";

import { PRIVACY_QUERY_KEY } from "./privacyQuery";
import { SettingsField } from "./SettingsField";

export function PrivacySettings() {
  const qc = useQueryClient();
  const { data, isPending, error } = useQuery({
    queryKey: PRIVACY_QUERY_KEY,
    queryFn: getPrivacySettings,
    retry: false,
    meta: { shownInline: true },
  });

  const setConsent = useMutation({
    mutationFn: async (next: boolean) =>
      updatePrivacySettings({ evalDataConsent: next }),
    onSuccess: (next: PrivacySettingsValue) => {
      qc.setQueryData(PRIVACY_QUERY_KEY, next);
    },
  });

  return (
    <div className="space-y-4">
      <SettingsField label="Improving PathFinder">
        <p className="text-sm leading-relaxed text-muted-foreground">
          PathFinder improves by learning from real strategies. We keep the science,
          never your identity. Finished investigations are stripped of anything that
          identifies you before a person reviews them, and turning this off also removes
          whatever of yours is still waiting for review.
        </p>
      </SettingsField>

      {isPending && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading privacy settings...
        </div>
      )}

      {error != null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          Failed to load privacy settings:{" "}
          {error instanceof Error ? error.message : "unknown error"}
        </div>
      )}

      {data != null && (
        <label className="flex items-center justify-between gap-4 rounded-md border border-border px-3 py-2.5">
          <span className="text-sm text-foreground">
            Let PathFinder learn from my strategies
          </span>
          <input
            type="checkbox"
            checked={data.evalDataConsent}
            disabled={setConsent.isPending}
            onChange={(e) => setConsent.mutate(e.target.checked)}
            className="h-4 w-4 accent-primary"
          />
        </label>
      )}

      {setConsent.error != null && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          Failed to save:{" "}
          {setConsent.error instanceof Error
            ? setConsent.error.message
            : "unknown error"}
        </div>
      )}
    </div>
  );
}
