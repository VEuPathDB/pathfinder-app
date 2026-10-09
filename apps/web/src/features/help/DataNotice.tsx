"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  PRIVACY_QUERY_KEY,
  continuePastDataNotice,
  getPrivacySettings,
} from "@/lib/api/privacy";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { useAuthRefresh } from "@/lib/query/hooks/useAuthRefresh";
import { yourDataUrl } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";

import { YOUR_DATA_IN_BRIEF, YOUR_DATA_LAST_UPDATED } from "./yourDataBrief";

const LEARN_ID = "data-notice-learn";
const LEARN_HELP_ID = "data-notice-learn-help";

export function DataNotice() {
  const qc = useQueryClient();
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { authRefreshed } = useAuthRefresh(selectedSite);
  const { data: authStatus } = useQuery(authStatusOptions(selectedSite));
  const { data } = useQuery({
    queryKey: PRIVACY_QUERY_KEY,
    queryFn: getPrivacySettings,
    staleTime: Infinity,
    retry: false,
    enabled: authRefreshed && authStatus?.signedIn === true,
  });
  const [learn, setLearn] = useState(true);
  const record = useMutation({
    mutationFn: continuePastDataNotice,
    onSuccess: (next) => {
      qc.setQueryData(PRIVACY_QUERY_KEY, next);
    },
  });

  return (
    <AlertDialog open={data?.noticeDue === true}>
      <AlertDialogContent className="max-h-[90vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>Your data in PathFinder</AlertDialogTitle>
          <AlertDialogDescription>
            Last updated: {YOUR_DATA_LAST_UPDATED}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-foreground">
          {YOUR_DATA_IN_BRIEF.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
        <Link
          href={yourDataUrl()}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary underline underline-offset-2"
        >
          Read the full statement
        </Link>
        <div className="flex items-start gap-3 rounded-md border border-border p-3">
          <Checkbox
            id={LEARN_ID}
            checked={learn}
            onCheckedChange={(next) => setLearn(next === true)}
            aria-describedby={LEARN_HELP_ID}
            className="mt-0.5"
          />
          <div className="space-y-1">
            <Label htmlFor={LEARN_ID}>Let PathFinder learn from my strategies</Label>
            <p
              id={LEARN_HELP_ID}
              className="text-xs leading-relaxed text-muted-foreground"
            >
              Copies of your conversations and strategies may be read by the team and
              used, without your name or account, to improve PathFinder for everyone.
              You can change this later in Settings, on the Privacy tab.
            </p>
          </div>
        </div>
        {record.isError && (
          <p role="alert" className="text-sm text-destructive">
            Your choice was not saved. Try again.
          </p>
        )}
        <AlertDialogFooter>
          <Button onClick={() => record.mutate(learn)} disabled={record.isPending}>
            Continue
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
