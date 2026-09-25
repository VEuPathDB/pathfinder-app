"use client";

import { GitBranch, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface BranchOrRevertDialogProps {
  open: boolean;
  canBranch: boolean;
  pending: boolean;
  error: string | null;
  onBranch: () => void;
  onRevert: () => void;
  onCancel: () => void;
}

export function BranchOrRevertDialog({
  open,
  canBranch,
  pending,
  error,
  onBranch,
  onRevert,
  onCancel,
}: BranchOrRevertDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit earlier message</DialogTitle>
          <DialogDescription>
            This message is not the latest one. Choose how to apply your edit.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-2 text-sm">
          <div className="flex items-start gap-3 rounded-md border border-border p-3">
            <GitBranch className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
            <div>
              <div className="font-medium">Branch to a new conversation</div>
              <div className="text-xs text-muted-foreground">
                Keep this conversation intact. Fork into a new conversation with history
                up to this point and send the edit there.
              </div>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-md border border-border p-3">
            <RotateCcw
              className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
              aria-hidden
            />
            <div>
              <div className="font-medium">Revert this conversation</div>
              <div className="text-xs text-muted-foreground">
                Delete every message after this point in this conversation. Notes and
                pending tasks from those turns are also removed. The strategy goes back
                to what it was at this message; a later version stays in your VEuPathDB
                account. Saved gene sets are kept.
              </div>
            </div>
          </div>
          {error !== null && (
            <p
              role="alert"
              data-testid="edit-dialog-error"
              className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive"
            >
              {error}
            </p>
          )}
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={onBranch}
              disabled={pending || !canBranch}
              data-testid="edit-branch-button"
            >
              <GitBranch className="mr-1 h-3.5 w-3.5" />
              Branch
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={onRevert}
              disabled={pending}
              data-testid="edit-revert-button"
            >
              <RotateCcw className="mr-1 h-3.5 w-3.5" />
              Revert
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
