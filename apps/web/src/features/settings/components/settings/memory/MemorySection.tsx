"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { MemoryItem } from "@pathfinder/shared";

import { MemoryRow } from "./MemoryRow";

interface MemorySectionProps {
  title: string;
  items: MemoryItem[];
  /** The memory a thread asked to show, marked in this list. */
  focusedKey?: string | null;
  onEdit: (item: MemoryItem) => void;
  onDelete: (item: MemoryItem) => void;
  onToggleAutoRetrieve: (item: MemoryItem, next: boolean) => void;
  defaultOpen?: boolean;
}

export function MemorySection({
  title,
  items,
  focusedKey = null,
  onEdit,
  onDelete,
  onToggleAutoRetrieve,
  defaultOpen = false,
}: MemorySectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <section className="rounded-md border border-border">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition hover:bg-muted/40"
      >
        <div className="flex items-center gap-2">
          <Chevron className="h-4 w-4 text-muted-foreground" aria-hidden />
          <span className="text-sm font-semibold text-foreground">{title}</span>
        </div>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {items.length}
        </span>
      </button>
      {open && (
        <div className="border-t border-border">
          {items.length === 0 ? (
            <div className="px-3 py-3 text-xs text-muted-foreground">
              No items stored yet.
            </div>
          ) : (
            <div>
              {items.map((item, idx) => (
                <MemoryRow
                  key={item.key === "" ? `${item.value.name}-${idx}` : item.key}
                  item={item}
                  focused={item.key === focusedKey}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  onToggleAutoRetrieve={onToggleAutoRetrieve}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
