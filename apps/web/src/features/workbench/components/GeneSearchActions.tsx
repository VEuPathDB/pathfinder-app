"use client";

import { useState } from "react";
import { Loader2, Plus, ThumbsDown, ThumbsUp } from "lucide-react";
import { createGeneSet } from "@/features/workbench/api/geneSets";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SaveControlSetForm } from "./SaveControlSetForm";

interface GeneSearchActionsProps {
  selectedIds: Set<string>;
  query: string;
  onClearSelection: () => void;
  onError: (err: string | null) => void;
}

export function GeneSearchActions({
  selectedIds,
  query,
  onClearSelection,
  onError,
}: GeneSearchActionsProps) {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const invalidateGeneSets = useInvalidateGeneSets();
  const evaluateOpen = useWorkbenchStore((s) => s.expandedPanels.has("evaluate"));
  const appendPositiveControls = useWorkbenchStore((s) => s.appendPositiveControls);
  const appendNegativeControls = useWorkbenchStore((s) => s.appendNegativeControls);

  const [showNameInput, setShowNameInput] = useState(false);
  const [newSetName, setNewSetName] = useState("");
  const [creating, setCreating] = useState(false);

  const hasSelection = selectedIds.size > 0;

  const handleCreateGeneSet = async () => {
    if (selectedIds.size === 0) return;
    const name = newSetName.trim() || `Search: ${query.trim()}`;
    setCreating(true);
    try {
      await createGeneSet({
        name,
        source: "paste",
        geneIds: [...selectedIds],
        siteId: selectedSite,
      });
      await invalidateGeneSets();
      onClearSelection();
      setShowNameInput(false);
      setNewSetName("");
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  };

  const handleAddPositive = () => {
    if (selectedIds.size === 0) return;
    appendPositiveControls([...selectedIds]);
    onClearSelection();
  };

  const handleAddNegative = () => {
    if (selectedIds.size === 0) return;
    appendNegativeControls([...selectedIds]);
    onClearSelection();
  };

  return (
    <div className="space-y-2 border-t border-border px-3 py-3">
      {showNameInput ? (
        <div className="flex items-center gap-1.5">
          <Input
            type="text"
            value={newSetName}
            onChange={(e) => setNewSetName(e.target.value)}
            placeholder={`Search: ${query.trim()}`}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreateGeneSet();
              if (e.key === "Escape") setShowNameInput(false);
            }}
            autoFocus
            className="h-7 flex-1 bg-background px-2 text-xs"
          />
          <Button
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => void handleCreateGeneSet()}
            disabled={creating}
          >
            {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : "Add"}
          </Button>
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="w-full text-xs"
          disabled={!hasSelection}
          onClick={() => setShowNameInput(true)}
        >
          <Plus className="h-3 w-3" />
          Create gene set ({selectedIds.size})
        </Button>
      )}

      <Button
        variant="outline"
        size="sm"
        className="w-full text-xs"
        disabled={!hasSelection || !evaluateOpen}
        onClick={handleAddPositive}
        title={!evaluateOpen ? "Open the Evaluate panel to use this" : undefined}
      >
        <ThumbsUp className="h-3 w-3" />
        Add to + controls ({selectedIds.size})
      </Button>

      <Button
        variant="outline"
        size="sm"
        className="w-full text-xs"
        disabled={!hasSelection || !evaluateOpen}
        onClick={handleAddNegative}
        title={!evaluateOpen ? "Open the Evaluate panel to use this" : undefined}
      >
        <ThumbsDown className="h-3 w-3" />
        {/* Use Unicode minus sign to match original */}
        Add to &minus; controls ({selectedIds.size})
      </Button>

      <SaveControlSetForm
        siteId={selectedSite}
        positiveIds={[...selectedIds]}
        negativeIds={[]}
      />
    </div>
  );
}
