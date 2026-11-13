"use client";

import type { SampledGene } from "@strategist/shared";
import { motion } from "motion/react";
import { useState } from "react";

import { Fold } from "@/lib/components/Fold";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import type { SpotCheck as SpotCheckModel } from "./reviewModel";
import { ReviewSection } from "./ReviewSection";

const FIT_ORDER = ["yes", "unclear", "no"] as const;

const FIT: Record<
  SampledGene["fits"],
  { bar: string; chip: string; word: string; one: string; many: string }
> = {
  yes: {
    bar: "bg-success",
    chip: "bg-success/10 text-success",
    word: "Fits",
    one: "fits",
    many: "fit",
  },
  unclear: {
    bar: "bg-warning/70",
    chip: "bg-warning/10 text-warning",
    word: "Unclear",
    one: "unclear",
    many: "unclear",
  },
  no: {
    bar: "bg-destructive/80",
    chip: "bg-destructive/10 text-destructive",
    word: "Does not fit",
    one: "does not fit",
    many: "do not fit",
  },
};

function GeneRow({ gene }: { gene: SampledGene }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-t border-border">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full flex-col gap-0.5 py-1.5 text-left transition-colors duration-120 hover:bg-muted/60"
      >
        <span className="flex w-full items-baseline justify-between gap-2">
          <span className="min-w-0 text-xs">
            <span className="font-mono text-primary">{gene.geneId}</span>
            {gene.product !== undefined && gene.product !== "" && (
              <span className="text-muted-foreground"> {gene.product}</span>
            )}
          </span>
          <span
            className={cn(
              "shrink-0 rounded-full px-2 py-px text-xs font-medium",
              FIT[gene.fits].chip,
            )}
          >
            {FIT[gene.fits].word}
          </span>
        </span>
        {open && <span className="text-xs text-muted-foreground">{gene.why}</span>}
      </button>
    </li>
  );
}

export function SpotCheck({ check }: { check: SpotCheckModel | null }) {
  const grow = useEntrance({
    initial: { flexGrow: 0 },
    transition: { type: "spring", stiffness: 260, damping: 30 },
  });
  if (check === null) return null;
  const total = check.genes.length;
  return (
    <ReviewSection
      title={`Spot check of ${total} results`}
      meta="Read from each record"
    >
      <div
        role="img"
        aria-label={FIT_ORDER.map(
          (fit) => `${check[fit]} ${check[fit] === 1 ? FIT[fit].one : FIT[fit].many}`,
        ).join(", ")}
        className="flex h-2 gap-0.5 overflow-hidden rounded-full"
      >
        {FIT_ORDER.filter((fit) => check[fit] > 0).map((fit) => (
          <motion.i
            key={fit}
            {...grow}
            animate={{ flexGrow: check[fit] }}
            className={cn("block basis-0", FIT[fit].bar)}
          />
        ))}
      </div>
      <p className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-muted-foreground">
        {FIT_ORDER.map((fit) => (
          <span key={fit} className="inline-flex items-center gap-1.5">
            <i
              className={cn("inline-block size-2 rounded-sm", FIT[fit].bar)}
              aria-hidden
            />
            <b className="font-semibold tabular-nums text-foreground">{check[fit]}</b>
            {check[fit] === 1 ? FIT[fit].one : FIT[fit].many}
          </span>
        ))}
      </p>
      <Fold title={`Show the ${total} genes`}>
        <ul className="flex flex-col">
          {check.genes.map((gene) => (
            <GeneRow key={gene.geneId} gene={gene} />
          ))}
        </ul>
      </Fold>
    </ReviewSection>
  );
}
