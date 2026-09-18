"use client";

import { useState } from "react";
import { siteDisplayName } from "@pathfinder/shared";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";

interface DeleteConversationModalProps {
  target: ConversationItem | null;
  isDeleting: boolean;
  onClose: () => void;
  onConfirmDelete: (options: { deleteLinkedStrategy: boolean }) => void;
}

export function DeleteConversationModal({
  target,
  isDeleting,
  onClose,
  onConfirmDelete,
}: DeleteConversationModalProps) {
  const [deleteLinkedStrategy, setDeleteLinkedStrategy] = useState(false);
  const [lastTargetId, setLastTargetId] = useState<string | null>(null);

  // Reset the opt-in whenever the target changes (render-time, no effect).
  const currentId = target?.id ?? null;
  if (currentId !== lastTargetId) {
    setLastTargetId(currentId);
    if (deleteLinkedStrategy) setDeleteLinkedStrategy(false);
  }

  const hasStrategy = target?.chat.wdkStrategyId != null;
  const dbName = target != null ? siteDisplayName(target.siteId) : "";
  const whose =
    target?.chat.wdkStrategyCreatedHere === true
      ? `PathFinder created this strategy in ${dbName}.`
      : `PathFinder has no record of creating this strategy in ${dbName}, so it may be one you made there yourself.`;

  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete conversation</DialogTitle>
          <DialogDescription>
            Delete{" "}
            <span className="font-semibold text-foreground">
              &ldquo;{target?.title}&rdquo;
            </span>
            ? It moves to Recently deleted and can be restored later.
          </DialogDescription>
        </DialogHeader>
        {hasStrategy && (
          <label className="mt-2 flex cursor-pointer items-start gap-2 rounded-md border border-border p-3 text-sm">
            <input
              type="checkbox"
              checked={deleteLinkedStrategy}
              onChange={(e) => setDeleteLinkedStrategy(e.target.checked)}
              disabled={isDeleting}
              className="mt-0.5 h-4 w-4 rounded border-input"
            />
            <div className="space-y-0.5">
              <div className="font-medium">Also delete strategy from {dbName}</div>
              <p
                data-testid="delete-linked-strategy-note"
                className="text-xs text-muted-foreground"
              >
                {whose} Deleting it is permanent, and the conversation will not be
                recoverable.
              </p>
            </div>
          </label>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => onConfirmDelete({ deleteLinkedStrategy })}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
