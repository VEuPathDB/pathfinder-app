"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Modal } from "@/lib/components/Modal";
import { SetVenn } from "@/features/workbench/components/SetVenn";
import { Button } from "@/components/ui/button";
import { createGeneSet } from "../api/geneSets";
import type { GeneSet } from "@pathfinder/shared";
import { useSessionStore } from "@/state/useSessionStore";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";

interface OverlapModalProps {
  open: boolean;
  onClose: () => void;
  sets: GeneSet[];
}

interface PairwiseResult {
  nameA: string;
  nameB: string;
  sizeA: number;
  sizeB: number;
  shared: number;
  jaccard: number;
}

export function OverlapModal({ open, onClose, sets }: OverlapModalProps) {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const invalidateGeneSets = useInvalidateGeneSets();

  const [clickedRegion, setClickedRegion] = useState<{
    label: string;
    geneIds: string[];
  } | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async (region: { label: string; geneIds: string[] }) => {
      return createGeneSet({
        name: region.label,
        source: "derived",
        geneIds: region.geneIds,
        siteId: selectedSite,
      });
    },
    onSuccess: async (gs) => {
      await invalidateGeneSets();
      setCreateSuccess(`Created "${gs.name}" with ${gs.geneIds.length} genes`);
    },
  });

  const unresolvedSets = sets.filter(
    (s) => s.geneIds.length === 0 && s.wdkStepId != null,
  );

  const resolvedSets = sets.filter((s) => s.geneIds.length > 0);

  const analysis = (() => {
    // Pairwise comparisons
    const pairwise: PairwiseResult[] = [];
    for (let i = 0; i < sets.length; i++) {
      const setI = sets[i];
      if (setI == null) continue;
      for (let j = i + 1; j < sets.length; j++) {
        const setJ = sets[j];
        if (setJ == null) continue;
        const idsA = setI.geneIds;
        const idsB = setJ.geneIds;
        const a = new Set(idsA);
        const b = new Set(idsB);
        const shared = idsA.filter((id) => b.has(id)).length;
        const unionSize = new Set([...idsA, ...idsB]).size;
        pairwise.push({
          nameA: setI.name,
          nameB: setJ.name,
          sizeA: a.size,
          sizeB: b.size,
          shared,
          jaccard: unionSize > 0 ? shared / unionSize : 0,
        });
      }
    }

    // Universal genes (in ALL sets)
    const allSets = sets.map((s) => new Set(s.geneIds));
    const allGenes = new Set(sets.flatMap((s) => s.geneIds));
    const universal = [...allGenes].filter((g) => allSets.every((s) => s.has(g)));

    // Total unique genes
    const totalUnique = allGenes.size;

    return { pairwise, universal, totalUnique };
  })();

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Gene Set Overlap"
      maxWidth="max-w-3xl"
      showCloseButton
    >
      <div className="p-5 space-y-5">
        {/* Warning for unresolved strategy-backed sets */}
        {unresolvedSets.length > 0 && (
          <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            Overlap cannot be computed for strategy-backed sets without resolved gene
            IDs: {unresolvedSets.map((s) => s.name).join(", ")}
          </div>
        )}

        {/* Summary */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-center">
            <p className="text-lg font-semibold">{sets.length}</p>
            <p className="text-[11px] text-muted-foreground">Gene Sets</p>
          </div>
          <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-center">
            <p className="text-lg font-semibold">
              {analysis.totalUnique.toLocaleString()}
            </p>
            <p className="text-[11px] text-muted-foreground">Unique Genes</p>
          </div>
          <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-center">
            <p className="text-lg font-semibold">
              {analysis.universal.length.toLocaleString()}
            </p>
            <p className="text-[11px] text-muted-foreground">In All Sets</p>
          </div>
        </div>

        {/* Multi-set Venn/Euler diagram */}
        {resolvedSets.length >= 2 && resolvedSets.length <= 5 && (
          <div>
            <h4 className="text-xs font-semibold text-muted-foreground mb-2">
              Set Relationships
            </h4>
            <div className="flex justify-center rounded-md border border-border bg-background p-3">
              <SetVenn
                sets={resolvedSets.map((s) => ({
                  key: s.name,
                  geneIds: s.geneIds,
                }))}
                height={resolvedSets.length > 3 ? 320 : 260}
                width={420}
                onRegionClick={(geneIds, label) => setClickedRegion({ label, geneIds })}
              />
            </div>
          </div>
        )}

        {/* Clicked region gene list */}
        {clickedRegion && clickedRegion.geneIds.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-semibold text-muted-foreground">
                {clickedRegion.label} ({clickedRegion.geneIds.length} genes)
              </h4>
              <button
                type="button"
                onClick={() => {
                  setClickedRegion(null);
                  setCreateSuccess(null);
                  createMutation.reset();
                }}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
            </div>
            <div className="max-h-32 overflow-y-auto rounded-md border border-border bg-background p-2">
              <div className="flex flex-wrap gap-1">
                {clickedRegion.geneIds.map((id) => (
                  <span
                    key={id}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]"
                  >
                    {id}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  if (clickedRegion.geneIds.length > 0) {
                    createMutation.mutate(clickedRegion);
                  }
                }}
                loading={createMutation.isPending}
                disabled={createMutation.isPending}
                className="gap-1 text-xs"
              >
                <Plus className="h-3 w-3" />
                Create Gene Set
              </Button>
              {createSuccess != null && createSuccess !== "" && (
                <span className="text-xs text-success">{createSuccess}</span>
              )}
              {createMutation.error != null && (
                <span className="text-xs text-destructive">
                  {createMutation.error.message}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Per-set summary */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground mb-2">Per Set</h4>
          <div className="space-y-1">
            {sets.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-1.5"
              >
                <span className="text-sm font-medium truncate mr-2">{s.name}</span>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {s.geneIds.length.toLocaleString()} genes
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Pairwise table */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground mb-2">
            Pairwise Overlap
          </h4>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                    Set A
                  </th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                    Set B
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Shared
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Jaccard
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Overlap %
                  </th>
                </tr>
              </thead>
              <tbody>
                {analysis.pairwise.map((p, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td
                      className="px-3 py-2 font-medium truncate max-w-[120px]"
                      title={p.nameA}
                    >
                      {p.nameA}
                    </td>
                    <td
                      className="px-3 py-2 font-medium truncate max-w-[120px]"
                      title={p.nameB}
                    >
                      {p.nameB}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {p.shared.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {p.jaccard.toFixed(3)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {Math.min(p.sizeA, p.sizeB) > 0
                        ? ((p.shared / Math.min(p.sizeA, p.sizeB)) * 100).toFixed(1)
                        : "0.0"}
                      %
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Universal genes */}
        {analysis.universal.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-muted-foreground mb-2">
              Genes in All Sets ({analysis.universal.length})
            </h4>
            <div className="max-h-32 overflow-y-auto rounded-md border border-border bg-background p-2">
              <div className="flex flex-wrap gap-1">
                {analysis.universal.map((id) => (
                  <span
                    key={id}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]"
                  >
                    {id}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
