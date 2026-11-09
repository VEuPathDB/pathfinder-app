"use client";

import type { RecalledMemory } from "@pathfinder/shared";
import { recalledMemoriesPayloadSchema } from "@pathfinder/shared/generated/zod/recalledMemoriesPayloadSchema";
import type { UIMessage } from "ai";

import { Button } from "@/components/ui/button";
import { Fold } from "@/lib/components/Fold";
import { MEMORY_KIND_LABELS } from "@/lib/memoryKinds";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";
import { useSettingsModalStore } from "@/state/useSettingsModalStore";

import { ReviewSection } from "./ReviewSection";

export function recalledMemories(messages: readonly UIMessage[]): RecalledMemory[] {
  const byKey = new Map<string, RecalledMemory>();
  for (const part of messages.flatMap((m) => m.parts)) {
    if (part.type !== "data-memory-retrieved" || !("data" in part)) continue;
    const parsed = recalledMemoriesPayloadSchema.safeParse(part.data);
    if (!parsed.success) continue;
    for (const memory of parsed.data.memories) byKey.set(memory.key, memory);
  }
  return [...byKey.values()];
}

export function MemoryFold({ messages }: { messages: readonly UIMessage[] }) {
  const focusMemory = useMemoryFocusStore((s) => s.focusMemory);
  const openSettings = useSettingsModalStore((s) => s.open);
  const memories = recalledMemories(messages);
  return (
    <ReviewSection>
      <Fold
        title="Memory"
        meta={memories.length === 0 ? "none used" : `${memories.length} used`}
      >
        <div className="flex flex-col gap-2">
          {memories.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              This conversation used nothing remembered from earlier conversations.
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {memories.map((memory) => (
                <li key={memory.key} className="flex items-baseline gap-2 text-sm">
                  <span className="shrink-0 rounded bg-muted px-1.5 text-xs text-muted-foreground">
                    {MEMORY_KIND_LABELS[memory.kind].one}
                  </span>
                  <button
                    type="button"
                    onClick={() => focusMemory(memory.key, memory.kind)}
                    className="min-w-0 truncate text-left text-foreground transition-colors duration-120 hover:text-primary"
                  >
                    {memory.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openSettings("memory")}
            className="h-7 self-start px-2 text-xs text-primary"
          >
            Manage memory
          </Button>
        </div>
      </Fold>
    </ReviewSection>
  );
}
