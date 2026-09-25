"use client";

import { useQuery } from "@tanstack/react-query";
import { Brain, Loader2 } from "lucide-react";
import type { MemoryItem } from "@pathfinder/shared";

import { listMemories } from "@/features/settings/api/memories";
import { MEMORY_KIND_LABELS, memorySections } from "@/lib/memoryKinds";

import { RailEmptyState, RailPanelShell } from "./RailPanelShell";

export function MemoriesPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["memories", "rail"] as const,
    queryFn: () => listMemories({ limit: 25, offset: 0 }),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });

  const sections = memorySections(data);

  const totalCount = sections.reduce((sum, s) => sum + s.items.length, 0);

  return (
    <RailPanelShell title="Memories">
      {isLoading && totalCount === 0 ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : totalCount === 0 ? (
        <RailEmptyState
          icon={<Brain className="h-8 w-8" aria-hidden />}
          heading="No memories yet"
          description="What the assistant keeps across conversations, and anything you ask it to remember, appears here."
        />
      ) : (
        <div className="divide-y divide-border">
          {sections.map((section) =>
            section.items.length > 0 ? (
              <MemorySection
                key={section.kind}
                title={MEMORY_KIND_LABELS[section.kind].many}
                items={section.items}
              />
            ) : null,
          )}
        </div>
      )}
    </RailPanelShell>
  );
}

function MemorySection({ title, items }: { title: string; items: MemoryItem[] }) {
  return (
    <div className="px-3 py-2">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title} · {items.length}
      </p>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item.key} className="rounded-md border border-border px-2 py-1.5">
            <p className="truncate text-xs font-medium">{item.value.name}</p>
            {item.value.summary.length > 0 && (
              <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                {item.value.summary}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
