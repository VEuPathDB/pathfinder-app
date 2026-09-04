"use client";

import { useState } from "react";
import {
  Trash2,
  Download,
  GitCompare,
  Layers,
  CheckSquare,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { deleteGeneSet } from "../api/geneSets";
import { exportAsTxt, exportAsCsv, exportMultipleAsCsv } from "../utils/export";
import { useShallow } from "zustand/react/shallow";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";
import type { GeneSet } from "@pathfinder/shared";
import { DeleteConfirmDialog } from "./DeleteConfirmDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface SelectionToolbarProps {
  activeSet: GeneSet | null;
  selectedSets: GeneSet[];
  allSetIds: string[];
  onCompare: () => void;
  onOverlap: () => void;
}

export function SelectionToolbar({
  activeSet,
  selectedSets,
  allSetIds,
  onCompare,
  onOverlap,
}: SelectionToolbarProps) {
  const { selectAll, deselectAll, clearSelection } = useWorkbenchStore(
    useShallow((s) => ({
      selectAll: s.selectAll,
      deselectAll: s.deselectAll,
      clearSelection: s.clearSelection,
    })),
  );
  const invalidateGeneSets = useInvalidateGeneSets();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const toDelete =
    selectedSets.length > 0 ? selectedSets : activeSet ? [activeSet] : [];
  const hasExactlyTwo = selectedSets.length === 2;
  const hasTwoOrMore = selectedSets.length >= 2;

  const handleDeleteRequest = () => {
    if (toDelete.length === 0) return;
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
    setShowDeleteConfirm(false);
    setDeleting(true);
    setDeleteError(null);
    try {
      await Promise.all(toDelete.map((gs) => deleteGeneSet(gs.id)));
      clearSelection();
      await invalidateGeneSets();
    } catch (err) {
      console.error("Failed to delete gene set(s):", err);
      setDeleteError("Some gene sets could not be deleted. Please try again.");
    } finally {
      setDeleting(false);
    }
  };

  const exportTarget =
    selectedSets.length > 0 ? selectedSets : activeSet ? [activeSet] : [];

  return (
    <>
      <div className="border-t border-border px-3 py-2.5">
        {/* Selection summary */}
        {allSetIds.length > 0 && (
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[10px] text-muted-foreground">
              {selectedSets.length > 0
                ? `${selectedSets.length} selected`
                : "None selected"}
            </p>
            <button
              type="button"
              onClick={
                selectedSets.length === allSetIds.length
                  ? deselectAll
                  : () => selectAll(allSetIds)
              }
              className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            >
              {selectedSets.length === allSetIds.length ? (
                <>
                  <Square className="h-3 w-3" /> Deselect all
                </>
              ) : (
                <>
                  <CheckSquare className="h-3 w-3" /> Select all
                </>
              )}
            </button>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap gap-1.5">
          <Button
            variant="outline"
            size="sm"
            disabled={toDelete.length === 0 || deleting}
            loading={deleting}
            onClick={handleDeleteRequest}
            className="gap-1 text-xs"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {toDelete.length > 1 ? `Delete (${toDelete.length})` : "Delete"}
          </Button>

          {hasExactlyTwo && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCompare}
              className="gap-1 text-xs"
            >
              <GitCompare className="h-3.5 w-3.5" />
              Compare
            </Button>
          )}

          {hasTwoOrMore && (
            <Button
              variant="outline"
              size="sm"
              onClick={onOverlap}
              className="gap-1 text-xs"
            >
              <Layers className="h-3.5 w-3.5" />
              Overlap
            </Button>
          )}

          {exportTarget.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1 text-xs">
                  <Download className="h-3.5 w-3.5" />
                  Export
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top">
                {(() => {
                  const singleTarget =
                    exportTarget.length === 1 ? exportTarget[0] : null;
                  return singleTarget != null ? (
                    <>
                      <DropdownMenuItem onClick={() => exportAsCsv(singleTarget)}>
                        Export as CSV
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => exportAsTxt(singleTarget)}>
                        Export as TXT
                      </DropdownMenuItem>
                    </>
                  ) : null;
                })()}
                {exportTarget.length > 1 && (
                  <DropdownMenuItem onClick={() => exportMultipleAsCsv(exportTarget)}>
                    Export {exportTarget.length} sets as CSV
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {deleteError != null && deleteError !== "" && (
          <p className="mt-2 text-xs text-destructive" role="alert">
            {deleteError}
          </p>
        )}
      </div>

      <DeleteConfirmDialog
        open={showDeleteConfirm}
        count={toDelete.length}
        onConfirm={() => {
          void handleDeleteConfirm();
        }}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}
