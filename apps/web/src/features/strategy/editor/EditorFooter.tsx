"use client";

import { ExternalLink } from "lucide-react";
import { siteShortName } from "@pathfinder/shared";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils/cn";
import { countNoun } from "@/lib/utils/countNoun";

export type SyncState = "idle" | "saving" | "error";

interface EditorFooterProps {
  syncState: SyncState;
  changeCount: number;
  isSaving: boolean;
  onSave: () => void;
  onDiscard: () => void;
  /** Result count from useStepCounts. null = loading. -1 = unknown. */
  count: number | null;
  /** The step's record type. It sets the noun the count reads as. */
  recordType: string | null | undefined;
  wdkUrl: string | null;
  /** Site the strategy belongs to. The link names it. */
  siteId: string;
}

function SyncDot({ state }: { state: SyncState }) {
  const className = cn(
    "inline-block size-2 rounded-full",
    state === "idle" && "bg-success",
    state === "saving" && "bg-primary",
    state === "error" && "bg-destructive",
  );
  return <span className={className} aria-hidden />;
}

export function EditorFooter({
  syncState,
  changeCount,
  isSaving,
  onSave,
  onDiscard,
  count,
  recordType,
  wdkUrl,
  siteId,
}: EditorFooterProps) {
  const hasChanges = changeCount > 0;
  const openLabel = `Open in ${siteId !== "" ? siteShortName(siteId) : "VEuPathDB"}`;
  return (
    <div
      className="flex flex-col gap-2 border-t border-border px-4 py-3 text-xs text-muted-foreground"
      data-testid="step-editor-footer"
    >
      <div className="flex items-center justify-between gap-3">
        <div
          className="flex items-center gap-2"
          data-testid="step-editor-sync-state"
          data-sync-state={syncState}
          data-change-count={changeCount}
        >
          {isSaving ? (
            <>
              <Spinner className="size-3" />
              <span>Saving...</span>
            </>
          ) : syncState === "error" ? (
            <>
              <SyncDot state="error" />
              <span className="text-destructive">Save failed</span>
            </>
          ) : hasChanges ? (
            <>
              <SyncDot state="saving" />
              <span data-testid="step-editor-change-count">
                Edited: {changeCount} {changeCount === 1 ? "change" : "changes"}
              </span>
            </>
          ) : (
            <>
              <SyncDot state="idle" />
              <span>All changes saved</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {count === null ? (
            <Skeleton className="h-3 w-12" />
          ) : count >= 0 ? (
            <span>
              {count.toLocaleString()} {countNoun(recordType, count)}
            </span>
          ) : null}
          {wdkUrl != null && (
            <a
              href={wdkUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={openLabel}
              className="inline-flex items-center gap-1 text-foreground hover:underline"
            >
              {openLabel}
              <ExternalLink className="size-3" aria-hidden />
            </a>
          )}
        </div>
      </div>
      {hasChanges && (
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onDiscard}
            disabled={isSaving}
            data-testid="step-editor-discard"
          >
            Discard
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={onSave}
            disabled={isSaving}
            data-testid="step-editor-save"
          >
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </div>
      )}
    </div>
  );
}
