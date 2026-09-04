"use client";

import { useRef, useState } from "react";
import { useOnClickOutside } from "usehooks-ts";
import { Database } from "lucide-react";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";

interface GeneSetPickerProps {
  onSelect: (geneIds: string[]) => void;
}

export function GeneSetPicker({ onSelect }: GeneSetPickerProps) {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const setsWithGenes = geneSets.filter((gs) => gs.geneIds.length > 0);

  useOnClickOutside(ref as React.RefObject<HTMLElement>, () => setOpen(false));

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={setsWithGenes.length === 0}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 rounded-md border border-input px-2.5 py-1 text-xs text-muted-foreground transition-colors duration-150 hover:border-foreground/30 hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Database className="h-3 w-3" />
        From Gene Set
      </button>

      {open && setsWithGenes.length > 0 && (
        <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-md border border-border bg-popover shadow-lg animate-hover-card-in">
          {setsWithGenes.map((gs) => (
            <button
              key={gs.id}
              type="button"
              onClick={() => {
                onSelect(gs.geneIds);
                setOpen(false);
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-xs transition-colors duration-75 hover:bg-accent"
            >
              <span className="truncate font-medium text-foreground">{gs.name}</span>
              <span className="shrink-0 text-muted-foreground">
                {gs.geneCount} genes
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
