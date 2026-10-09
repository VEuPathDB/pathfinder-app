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
      <SettingsField label="Learning from your strategies">
        <p
          data-testid="privacy-learning-copy"
          className="text-sm leading-relaxed text-muted-foreground"
        >
          When this is on, PathFinder may use copies of your conversations and
          strategies to improve PathFinder for everyone, for example for review by the
          team, as test cases, or as shared examples the assistant draws on. A copy used
          beyond review never carries your name, your account or a link to your
          conversation. Today, PathFinder copies your finished conversations each night,
          and a conversation when you dislike one of its replies. Turning this off
          deletes your copies that are waiting for review and stops new ones.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          More in{" "}
          <Link
            href={yourDataUrl("learning")}
            className="text-primary underline underline-offset-2"
          >
            Your data in PathFinder
          </Link>
          .
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
