"use client";

import { Trash2, Unlink } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface OrphanNoticeProps {
  count: number;
  /** First orphan step id, used by the "View" affordance to scroll the user to it. */
  firstOrphanId: string | null;
  onClickFirst?: ((stepId: string) => void) | undefined;
  onRemoveAll?: (() => void) | undefined;
}

export function OrphanNotice({
  count,
  firstOrphanId,
  onClickFirst,
  onRemoveAll,
}: OrphanNoticeProps) {
  if (count <= 0) return null;
  return (
    <Alert
      data-testid="orphan-notice"
      className="pointer-events-auto w-auto max-w-2xl border-warning/40 bg-warning/10 text-warning *:data-[slot=alert-description]:text-warning [&>svg]:text-warning"
    >
      <Unlink className="size-4" aria-hidden />
      <AlertTitle className="flex items-center justify-between gap-3">
        <span>
          {count} disconnected {count === 1 ? "step" : "steps"} - not pushed
        </span>
        <span className="flex items-center gap-1">
          {firstOrphanId !== null && onClickFirst !== undefined && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onClickFirst(firstOrphanId)}
              className="h-7 px-2 text-warning hover:bg-warning/20 hover:text-warning"
            >
              View -&gt;
            </Button>
          )}
          {onRemoveAll !== undefined && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onRemoveAll}
              className="h-7 gap-1 px-2 text-warning hover:bg-warning/20 hover:text-warning"
            >
              <Trash2 className="size-3.5" aria-hidden />
              Remove all
            </Button>
          )}
        </span>
      </AlertTitle>
      <AlertDescription>
        Reconnect them to the strategy or remove them. Only the rooted graph is pushed.
      </AlertDescription>
    </Alert>
  );
}
