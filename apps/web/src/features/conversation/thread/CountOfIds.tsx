"use client";

import { toast } from "sonner";
import type { ReactElement } from "react";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

interface CountOfIdsProps {
  count: number;
  /** Every id the count stands for, or none when the count carries no ids. */
  ids: readonly string[];
  /** What the ids are, read in the card and in the copy message. */
  noun: string;
}

/** A count that shows the ids behind it, and copies them when clicked. */
export function CountOfIds({ count, ids, noun }: CountOfIdsProps): ReactElement {
  const reading = count.toLocaleString();
  if (ids.length === 0) return <span>{reading}</span>;
  const copy = () => {
    void navigator.clipboard.writeText(ids.join(", "));
    toast.success(`${ids.length.toLocaleString()} gene ids copied`);
  };
  return (
    <HoverCard openDelay={80} closeDelay={80}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          data-testid="count-of-ids"
          aria-label={`${reading} ${noun}, click to copy the ids`}
          className="underline decoration-dotted decoration-from-font underline-offset-4 hover:decoration-solid"
          onClick={copy}
        >
          {reading}
        </button>
      </HoverCardTrigger>
      <HoverCardContent className="w-72 p-3">
        <p className="text-[11px] text-muted-foreground">{noun}</p>
        <p className="mt-1.5 max-h-40 overflow-y-auto font-mono text-[11px] break-all text-foreground">
          {ids.join(", ")}
        </p>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          Click the number to copy them.
        </p>
      </HoverCardContent>
    </HoverCard>
  );
}
