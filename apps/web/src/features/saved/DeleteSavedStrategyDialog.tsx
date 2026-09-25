"use client";

import { siteShortName } from "@pathfinder/shared";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface DeleteSavedStrategyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  siteId: string;
  onConfirm: () => void;
}

/** Asks before a saved strategy is deleted here and on its site. */
export function DeleteSavedStrategyDialog({
  open,
  onOpenChange,
  name,
  siteId,
  onConfirm,
}: DeleteSavedStrategyDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{`Delete "${name}"?`}</AlertDialogTitle>
          <AlertDialogDescription>
            {`This also deletes the strategy on ${siteShortName(siteId)}, and PathFinder cannot restore it.`}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
