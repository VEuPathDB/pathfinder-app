import Link from "next/link";

import type { RecalledMemoriesPayload, RecalledMemory } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";
import { MEMORY_KIND_LABELS } from "@/lib/memoryKinds";
import { chatUrl } from "@/lib/routes";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";
import { useSessionStore } from "@/state/useSessionStore";

const NAME = "min-w-0 truncate text-left";
const WRITTEN: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
};

/** The names that more than one memory carries. */
function repeatedNames(memories: RecalledMemory[]): Set<string> {
  const counts = new Map<string, number>();
  for (const m of memories) counts.set(m.name, (counts.get(m.name) ?? 0) + 1);
  return new Set([...counts].filter(([, n]) => n > 1).map(([name]) => name));
}

function MemoryName({ memory }: { memory: RecalledMemory }) {
  const siteId = useSessionStore((s) => s.selectedSite);
  const focusMemory = useMemoryFocusStore((s) => s.focusMemory);
  if (memory.kind === "strategy") {
    const thread = memory.sourceConversationId;
    if (thread == null) {
      return (
        <span className={NAME} title={memory.name}>
          {memory.name}
        </span>
      );
    }
    return (
      <Link
        href={chatUrl(siteId, thread)}
        className={`${NAME} hover:underline`}
        title={memory.name}
      >
        {memory.name}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={() => focusMemory(memory.key, memory.kind)}
      className={`${NAME} hover:underline`}
      title={memory.name}
    >
      {memory.name}
    </button>
  );
}

export function DataMemoryRetrieved({ data }: { data: RecalledMemoriesPayload }) {
  const memories = data.memories;
  if (memories.length === 0) return null;
  const repeated = repeatedNames(memories);
  const count = memories.length;
  return (
    <Figure
      testId="data-memory-retrieved"
      title="Recalled memories"
      caption={`${count.toLocaleString()} ${count === 1 ? "memory" : "memories"}`}
    >
      <div className="text-xs">
        <ul className="space-y-0.5">
          {memories.map((mem) => (
            <li key={mem.key} className="flex min-w-0 items-baseline gap-2">
              <span className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px]">
                {MEMORY_KIND_LABELS[mem.kind].one}
              </span>
              <MemoryName memory={mem} />
              {repeated.has(mem.name) && (
                <span
                  data-testid="memory-written"
                  className="shrink-0 text-muted-foreground"
                >
                  {new Date(mem.createdAt).toLocaleString(undefined, WRITTEN)}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </Figure>
  );
}
