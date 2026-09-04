"use client";

import { Modal } from "@/lib/components/Modal";
import { SetVenn } from "@/features/workbench/components/SetVenn";
import type { GeneSet } from "@pathfinder/shared";

interface CompareModalProps {
  open: boolean;
  onClose: () => void;
  setA: GeneSet;
  setB: GeneSet;
}

export function CompareModal({ open, onClose, setA, setB }: CompareModalProps) {
  const comparison = (() => {
    const idsA = setA.geneIds;
    const idsB = setB.geneIds;
    const a = new Set(idsA);
    const b = new Set(idsB);
    const shared = idsA.filter((id) => b.has(id));
    const onlyA = idsA.filter((id) => !b.has(id));
    const onlyB = idsB.filter((id) => !a.has(id));
    const unionSize = new Set([...idsA, ...idsB]).size;
    const jaccard = unionSize > 0 ? shared.length / unionSize : 0;
    return { shared, onlyA, onlyB, unionSize, jaccard };
  })();

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Compare Gene Sets"
      maxWidth="max-w-4xl"
      showCloseButton
    >
      <div className="p-5">
        {/* Stats */}
        <div className="grid grid-cols-5 gap-3 mb-5">
          {[
            { label: setA.name, value: setA.geneIds.length },
            { label: setB.name, value: setB.geneIds.length },
            { label: "Shared", value: comparison.shared.length },
            { label: "Union", value: comparison.unionSize },
            { label: "Jaccard Index", value: comparison.jaccard.toFixed(3) },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-md border border-border bg-muted/50 px-3 py-2 text-center"
            >
              <p className="text-lg font-semibold text-foreground">{stat.value}</p>
              <p
                className="text-[11px] text-muted-foreground truncate"
                title={stat.label}
              >
                {stat.label}
              </p>
            </div>
          ))}
        </div>

        {/* Proportional Venn diagram */}
        <div className="flex justify-center py-2">
          <SetVenn
            sets={[
              { key: setA.name, geneIds: setA.geneIds },
              { key: setB.name, geneIds: setB.geneIds },
            ]}
            height={200}
            width={320}
          />
        </div>

        {/* Three-column gene list */}
        <div className="grid grid-cols-3 gap-3">
          {[
            {
              title: `Only in ${setA.name}`,
              genes: comparison.onlyA,
              dot: "bg-[hsl(var(--chart-1))]",
            },
            {
              title: "Shared",
              genes: comparison.shared,
              dot: "bg-[hsl(var(--chart-2))]",
            },
            {
              title: `Only in ${setB.name}`,
              genes: comparison.onlyB,
              dot: "bg-[hsl(var(--chart-3))]",
            },
          ].map((col) => (
            <div key={col.title} className="flex flex-col">
              <h4 className="mb-2 text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                <span className={`inline-block h-2 w-2 rounded-full ${col.dot}`} />
                {col.title}
                <span className="ml-auto text-[10px] font-normal">
                  {col.genes.length}
                </span>
              </h4>
              <div className="flex-1 max-h-64 overflow-y-auto rounded-md border border-border bg-background p-2">
                {col.genes.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic">None</p>
                ) : (
                  <div className="space-y-0.5">
                    {col.genes.map((id) => (
                      <p key={id} className="font-mono text-xs text-foreground">
                        {id}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}
