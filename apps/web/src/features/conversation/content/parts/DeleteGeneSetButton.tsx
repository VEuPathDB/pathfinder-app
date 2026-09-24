"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

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
import { deleteGeneSet } from "@/lib/api/geneSets";

const PILL =
  "flex items-center gap-1 rounded-full border border-border px-2 py-0.5" +
  " text-[10px] font-medium text-muted-foreground hover:text-destructive" +
  " disabled:opacity-50";

type DeleteState =
  | { kind: "idle" }
  | { kind: "confirming" }
  | { kind: "deleting" }
  | { kind: "failed"; message: string };

interface DeleteGeneSetButtonProps {
  geneSetId: string;
  name: string;
  onDeleted: () => void;
}

/** Deletes one gene set after the researcher confirms it. */
export function DeleteGeneSetButton({
  geneSetId,
  name,
  onDeleted,
}: DeleteGeneSetButtonProps) {
  const [state, setState] = useState<DeleteState>({ kind: "idle" });

  const remove = async (): Promise<void> => {
    setState({ kind: "deleting" });
    try {
      await deleteGeneSet(geneSetId);
      setState({ kind: "idle" });
      onDeleted();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Delete failed";
      setState({ kind: "failed", message });
    }
  };

  return (
    <span className="flex items-center gap-1.5">
      <button
        type="button"
        aria-label="Delete gene set"
        onClick={() => setState({ kind: "confirming" })}
        disabled={state.kind === "deleting"}
        className={PILL}
      >
        <Trash2 className="size-3" aria-hidden />
        {state.kind === "deleting" ? "Deleting..." : "Delete"}
      </button>
      {state.kind === "failed" && (
        <span className="text-[10px] text-destructive">{state.message}</span>
      )}
      <AlertDialog
        open={state.kind === "confirming"}
        onOpenChange={(open) => {
          if (!open) setState({ kind: "idle" });
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{`Delete ${name}?`}</AlertDialogTitle>
            <AlertDialogDescription>
              PathFinder removes this gene set and cannot restore it. A dataset
              published from it stays in your VEuPathDB workspace.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void remove()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </span>
  );
}
