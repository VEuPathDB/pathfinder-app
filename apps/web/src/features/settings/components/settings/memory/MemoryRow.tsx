"use client";

import { Trash2 } from "lucide-react";
import type { MemoryItem } from "@pathfinder/shared";

import { cn } from "@/lib/utils/cn";

interface MemoryRowProps {
  item: MemoryItem;
  focused?: boolean;
  onEdit: (item: MemoryItem) => void;
  onDelete: (item: MemoryItem) => void;
  onToggleAutoRetrieve: (item: MemoryItem, next: boolean) => void;
}

function scrollIntoView(node: HTMLElement | null): void {
  node?.scrollIntoView({ block: "center" });
}

export function MemoryRow({
  item,
  focused = false,
  onEdit,
  onDelete,
  onToggleAutoRetrieve,
}: MemoryRowProps) {
  const v = item.value;
  const tags = v.tags ?? [];
  return (
    <div className="flex items-start gap-3 border-b border-border px-2 py-2 last:border-b-0">
      <input
        type="checkbox"
        checked={v.autoRetrieve}
        onChange={(e) => onToggleAutoRetrieve(item, e.target.checked)}
        className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-primary"
        aria-label={`Toggle auto-retrieve for ${v.name}`}
      />
      <button
        type="button"
        data-testid="memory-row-body"
        aria-current={focused ? "true" : undefined}
        ref={focused ? scrollIntoView : undefined}
        onClick={() => onEdit(item)}
        className={cn(
          "flex-1 min-w-0 text-left transition hover:bg-muted/40 rounded-md px-1.5 py-0.5",
          focused && "bg-primary/10 ring-1 ring-primary/40",
        )}
      >
        <div className="truncate text-sm font-medium text-foreground">{v.name}</div>
        {v.summary !== "" && (
          <div className="line-clamp-2 text-xs text-muted-foreground">{v.summary}</div>
        )}
        {tags.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </button>
      <button
        type="button"
        onClick={() => onDelete(item)}
        aria-label={`Delete ${v.name}`}
        className="shrink-0 rounded-md p-1 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
