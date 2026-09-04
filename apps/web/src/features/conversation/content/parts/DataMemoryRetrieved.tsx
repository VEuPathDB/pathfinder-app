import type { MemoryRetrievedPayload } from "@pathfinder/shared/generated/types/MemoryRetrievedPayload";

import { Figure } from "@/features/conversation/thread/Figure";

export function DataMemoryRetrieved({ data }: { data: MemoryRetrievedPayload }) {
  if (data.memories.length === 0) return null;
  return (
    <Figure
      testId="data-memory-retrieved"
      title="Recalled memories"
      caption={`${data.memories.length.toLocaleString()} memories`}
    >
      <div className="text-xs">
        <ul className="space-y-0.5">
          {data.memories.map((mem) => (
            <li key={mem.key} className="flex items-baseline gap-1.5">
              <span className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] font-mono">
                {mem.kind}
              </span>
              <span className="truncate">{mem.name}</span>
            </li>
          ))}
        </ul>
      </div>
    </Figure>
  );
}
