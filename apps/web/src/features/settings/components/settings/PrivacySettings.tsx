"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";

import type { PrivacySettings as PrivacySettingsValue } from "@pathfinder/shared";

import {
  PRIVACY_QUERY_KEY,
  getPrivacySettings,
  updatePrivacySettings,
} from "@/lib/api/privacy";
import { yourDataUrl } from "@/lib/routes";

import { SettingsSection, SettingsSwitch } from "./SettingsRow";

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
      <SettingsSection
        title="Learning from your strategies"
        description={
          <>
            <span data-testid="privacy-learning-copy">
              PathFinder may use copies of your conversations and strategies to improve
              it for everyone. A copy used beyond review never carries your name or
              account. Turning this off deletes the copies waiting for review.
            </span>{" "}
            <Link
              href={yourDataUrl("learning")}
              className="text-foreground underline underline-offset-2"
            >
              Your data in PathFinder
            </Link>
          </>
        }
      >
        {data != null && (
          <SettingsSwitch
            label="Let PathFinder learn from my strategies"
            checked={data.evalDataConsent}
            disabled={setConsent.isPending}
            onCheckedChange={(next) => setConsent.mutate(next)}
          />
        )}
      </SettingsSection>

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
