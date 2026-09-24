"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ExternalLink,
  ArrowLeft,
  Code2,
  Copy,
  Loader2,
  MoreVertical,
  PauseCircle,
  Pencil,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { siteShortName } from "@pathfinder/shared";
import type { Strategy } from "@pathfinder/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useDeleteStrategyMutation,
  useUpdateStrategyMetaMutation,
} from "@/features/strategy/mutations";
import { provisionalName } from "@/lib/conversations/provisionalName";
import { chatUrl, strategyCanvasUrl } from "@/lib/routes";
import { cn } from "@/lib/utils/cn";
import { useFirstMessageStore } from "@/state/useFirstMessageStore";
import { CanvasDescriptionSheet } from "./CanvasDescriptionSheet";
import { DeleteStrategyConfirm } from "./DeleteStrategyConfirm";

export type SyncState = "idle" | "saving" | "error" | "paused";

interface CanvasTopbarProps {
  strategy: Strategy;
  conversationId: string;
  syncState: SyncState;
  onRetry: () => void;
}

const isDevEnv = process.env.NODE_ENV === "development";

export function CanvasTopbar({
  strategy,
  conversationId,
  syncState,
  onRetry,
}: CanvasTopbarProps) {
  const router = useRouter();
  const updateMeta = useUpdateStrategyMetaMutation(conversationId);
  const deleteStrategy = useDeleteStrategyMutation();
  const [draftName, setDraftName] = useState(strategy.name);
  const [prevName, setPrevName] = useState(strategy.name);
  const [descSheetOpen, setDescSheetOpen] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const firstMessage = useFirstMessageStore(
    (s) => s.byConversation[conversationId] ?? null,
  );
  const shownName = provisionalName(strategy.name, firstMessage);

  if (strategy.name !== prevName) {
    setPrevName(strategy.name);
    setDraftName(strategy.name);
  }

  const commitName = (): void => {
    const next = draftName.trim();
    if (next === "" || next === strategy.name) {
      setDraftName(strategy.name);
      return;
    }
    updateMeta.mutate({ name: next });
  };

  const siteId = strategy.siteId;

  const handleBack = (): void => {
    router.push(chatUrl(siteId, conversationId));
  };

  const handleDelete = (): void => {
    setConfirmDeleteOpen(true);
  };

  const handleConfirmDelete = (): void => {
    deleteStrategy.mutate(
      { conversationId, siteId },
      { onSettled: () => setConfirmDeleteOpen(false) },
    );
  };

  const handleEditDescription = (): void => {
    setDescSheetOpen(true);
  };

  const handleCopyUrl = (): void => {
    if (typeof window === "undefined") return;
    const origin = window.location.origin;
    const url = `${origin}${strategyCanvasUrl(siteId, conversationId)}`;
    void navigator.clipboard.writeText(url);
    toast.success("Strategy URL copied");
  };

  const stepCount = strategy.steps.length;

  return (
    <div
      className="flex h-10 items-center gap-2 border-b border-border bg-background px-3"
      data-testid="canvas-topbar"
    >
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={handleBack}
        aria-label="Back to chat"
        data-testid="canvas-topbar-back"
        className="gap-1.5"
      >
        <ArrowLeft className="size-4" aria-hidden />
        <span className="text-xs">Back to chat</span>
      </Button>
      <div className="h-5 w-px bg-border" aria-hidden />
      <Input
        value={draftName}
        onChange={(event) => setDraftName(event.target.value)}
        onBlur={commitName}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          } else if (event.key === "Escape") {
            setDraftName(strategy.name);
            event.currentTarget.blur();
          }
        }}
        onFocus={(event) => event.currentTarget.select()}
        aria-label="Strategy name"
        placeholder={shownName}
        className="h-7 max-w-xs flex-1 text-sm"
      />
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span data-testid="canvas-topbar-step-count">
          {stepCount} {stepCount === 1 ? "step" : "steps"}
        </span>
        <span aria-hidden>-</span>
        <SyncStatusPill state={syncState} onRetry={onRetry} />
      </div>
      <div className="ml-auto flex items-center gap-1">
        {strategy.wdkUrl != null && strategy.wdkUrl !== "" && (
          <Button asChild type="button" variant="ghost" size="sm" className="gap-1.5">
            <a
              href={strategy.wdkUrl}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="canvas-topbar-wdk-link"
            >
              <span className="text-xs">{siteShortName(strategy.siteId)}</span>
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="More strategy actions"
            >
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[200px]">
            <DropdownMenuItem onSelect={handleEditDescription}>
              <Pencil className="size-4" />
              Edit description
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={handleCopyUrl}>
              <Copy className="size-4" />
              Copy strategy URL
            </DropdownMenuItem>
            {isDevEnv && (
              <DropdownMenuItem onSelect={() => setShowRaw((prev) => !prev)}>
                <Code2 className="size-4" />
                {showRaw ? "Hide" : "Show"} raw AST
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={handleDelete}>
              <Trash2 className="size-4" />
              Delete strategy
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <CanvasDescriptionSheet
        open={descSheetOpen}
        onOpenChange={setDescSheetOpen}
        initialDescription={strategy.description ?? ""}
        conversationId={conversationId}
      />
      <DeleteStrategyConfirm
        open={confirmDeleteOpen}
        strategyName={shownName}
        isDeleting={deleteStrategy.isPending}
        onCancel={() => setConfirmDeleteOpen(false)}
        onConfirm={handleConfirmDelete}
      />
      {isDevEnv && showRaw && (
        <pre
          data-testid="canvas-topbar-raw-ast"
          className="absolute right-3 top-12 z-50 max-h-[60vh] max-w-xl overflow-auto rounded border border-border bg-popover p-3 text-[10px] text-popover-foreground shadow"
        >
          {JSON.stringify(strategy, null, 2)}
        </pre>
      )}
    </div>
  );
}

interface SyncStatusPillProps {
  state: SyncState;
  onRetry: () => void;
}

function SyncStatusPill({ state, onRetry }: SyncStatusPillProps) {
  if (state === "saving") {
    return (
      <span
        className="inline-flex items-center gap-1 text-muted-foreground"
        data-testid="canvas-topbar-sync-state"
        data-sync-state="saving"
      >
        <Loader2 className="size-3 animate-spin" aria-hidden />
        Saving...
      </span>
    );
  }
  if (state === "error") {
    return (
      <button
        type="button"
        onClick={onRetry}
        data-testid="canvas-topbar-sync-state"
        data-sync-state="error"
        className={cn(
          "inline-flex items-center gap-1 text-destructive hover:underline",
        )}
      >
        <TriangleAlert className="size-3" aria-hidden />
        Failed - Retry
      </button>
    );
  }
  if (state === "paused") {
    return (
      <span
        className="inline-flex items-center gap-1 text-warning"
        data-testid="canvas-topbar-sync-state"
        data-sync-state="paused"
      >
        <PauseCircle className="size-3" aria-hidden />
        Sync paused
      </span>
    );
  }
  return (
    <span
      className="text-muted-foreground"
      data-testid="canvas-topbar-sync-state"
      data-sync-state="idle"
    >
      Saved
    </span>
  );
}
