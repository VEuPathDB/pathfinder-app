"use client";

import { useState } from "react";
import { Bookmark, Copy, MoreVertical, Trash2, Code2 } from "lucide-react";
import type { Step, StepKind } from "@pathfinder/shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils/cn";
import { stepSubtitle } from "@/features/strategy/graph/utils/stepTitle";
import { COPY_STEP_ACTION, hasACopy } from "@/features/strategy/copyStep";

interface EditorHeaderProps {
  step: Step;
  kind: StepKind;
  stepNumber: number | null;
  onRename: (next: string) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onCopyUrl: () => void;
  onSaveAsReusable: () => void;
}

const KIND_BG: Record<StepKind, string> = {
  search:
    "bg-[hsl(var(--kind-leaf)/0.15)] text-foreground hover:bg-[hsl(var(--kind-leaf)/0.15)]",
  combine:
    "bg-[hsl(var(--kind-combine)/0.15)] text-foreground hover:bg-[hsl(var(--kind-combine)/0.15)]",
  transform:
    "bg-[hsl(var(--kind-transform)/0.15)] text-foreground hover:bg-[hsl(var(--kind-transform)/0.15)]",
};

const isDevEnv = process.env.NODE_ENV === "development";

export function EditorHeader({
  step,
  kind,
  stepNumber,
  onRename,
  onDelete,
  onDuplicate,
  onCopyUrl,
  onSaveAsReusable,
}: EditorHeaderProps) {
  const initialName = step.displayName ?? "";
  const [draft, setDraft] = useState(initialName);
  const [showRaw, setShowRaw] = useState(false);

  const [prevInitial, setPrevInitial] = useState(initialName);
  if (initialName !== prevInitial) {
    setPrevInitial(initialName);
    setDraft(initialName);
  }

  const commit = (): void => {
    const next = draft.trim();
    if (next === "" || next === initialName) {
      setDraft(initialName);
      return;
    }
    onRename(next);
  };

  const cancel = (): void => {
    setDraft(initialName);
  };
  const subtitle = stepSubtitle(step, kind);

  return (
    <div className="border-b border-border py-3 pl-4 pr-12">
      <div className="flex items-center gap-2">
        <Badge
          variant="secondary"
          className={cn("uppercase tracking-wide", KIND_BG[kind])}
        >
          {kind}
        </Badge>
        {stepNumber != null && (
          <span className="text-xs text-muted-foreground">Step {stepNumber}</span>
        )}
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.currentTarget.blur();
            } else if (event.key === "Escape") {
              cancel();
              event.currentTarget.blur();
            }
          }}
          onFocus={(event) => event.currentTarget.select()}
          aria-label="Step name"
          className="h-8 flex-1"
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="More actions"
            >
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[180px]">
            {hasACopy(kind) && (
              <DropdownMenuItem onSelect={onDuplicate} title={COPY_STEP_ACTION.title}>
                <Copy className="size-4" />
                {COPY_STEP_ACTION.label}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onSelect={onCopyUrl}>
              <Copy className="size-4" />
              Copy step URL
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={onSaveAsReusable}
              data-testid="step-editor-save-substrategy"
            >
              <Bookmark className="size-4" />
              Save as reusable...
            </DropdownMenuItem>
            {isDevEnv && (
              <DropdownMenuItem onSelect={() => setShowRaw((prev) => !prev)}>
                <Code2 className="size-4" />
                {showRaw ? "Hide" : "Show"} raw JSON
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={onDelete}>
              <Trash2 className="size-4" />
              Delete step
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {subtitle !== "" && (
        <p
          className="mt-1 truncate text-xs text-muted-foreground"
          title={subtitle}
          data-testid="step-editor-subtitle"
        >
          {subtitle}
        </p>
      )}
      {isDevEnv && showRaw && (
        <pre className="absolute right-4 top-14 z-10 max-w-md rounded border border-border bg-popover p-2 text-[10px] text-popover-foreground shadow">
          {JSON.stringify(step, null, 2)}
        </pre>
      )}
    </div>
  );
}
